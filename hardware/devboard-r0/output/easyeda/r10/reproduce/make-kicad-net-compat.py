#!/usr/bin/env python3
"""Create an isolated import copy using legacy numeric KiCad net references.

Reference: https://dev-docs.kicad.org/en/file-formats/sexpr-pcb/
This is a targeted importer workaround, NOT a full KiCad version downgrade.
The version header, layer identifiers, geometry, stackup and schematic stay intact.
Run with /usr/bin/python3 (system pcbnew module).
"""
from pathlib import Path
import collections
import hashlib
import json
import re
import shutil
import zipfile
import pcbnew

BASE = Path(__file__).resolve().parent
SOURCE = BASE / 'source'
DEST = BASE / 'compat-source'
BOARD = 'ESPaperPlay_Devboard.kicad_pcb'
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+')

def convert(text):
    """Use parser stack and source spans; leave unrelated bytes unchanged."""
    stack, net_nodes, first_footprint = [], [], None
    for m in TOKEN.finditer(text):
        token = m.group()
        if token == '(':
            stack.append({'start': m.start(), 'atoms': [], 'children': []})
        elif token == ')':
            node = stack.pop()
            node['end'] = m.end()
            kind = node['atoms'][0] if node['atoms'] else ''
            parent = stack[-1]['atoms'][0] if stack else None
            if kind == 'footprint' and parent == 'kicad_pcb' and first_footprint is None:
                first_footprint = node['start']
            if kind == 'net':
                assert len(node['atoms']) == 2 and node['atoms'][1].startswith('"'), node
                assert parent in ('pad', 'segment', 'via', 'zone', 'arc'), parent
                net_nodes.append((node, parent, json.loads(node['atoms'][1])))
            if stack:
                stack[-1]['children'].append(kind)
        elif stack:
            stack[-1]['atoms'].append(token)
    assert not stack and first_footprint is not None
    names = [''] + sorted({name for _, _, name in net_nodes if name})
    ids = {name: i for i, name in enumerate(names)}
    patches = []
    for node, parent, name in net_nodes:
        quoted = json.dumps(name, ensure_ascii=False)
        if parent == 'pad':
            replacement = f'(net {ids[name]} {quoted})'
        elif parent == 'zone':
            replacement = f'(net {ids[name]})\n\t\t(net_name {quoted})'
        else:
            replacement = f'(net {ids[name]})'
        patches.append((node['start'], node['end'], replacement))
    table = '\n\t'.join(f'(net {i} {json.dumps(name, ensure_ascii=False)})' for i, name in enumerate(names))
    patches.append((first_footprint, first_footprint, table + '\n\t'))
    # Only selected net spans and a new top-level table change.
    output = text
    for start, end, replacement in sorted(patches, reverse=True):
        output = output[:start] + replacement + output[end:]
    return output, {'nonempty_nets': len(names)-1, 'rewritten_nodes': dict(collections.Counter(parent for _, parent, _ in net_nodes))}

def xy(p):
    return [p.x, p.y]

def snapshot(board):
    fps = []
    pads = []
    for f in board.GetFootprints():
        fps.append([f.m_Uuid.AsString(), f.GetReference(), f.GetValue(), xy(f.GetPosition()), f.GetOrientationDegrees(), f.GetLayer()])
        for p in f.Pads():
            pads.append([p.m_Uuid.AsString(), f.GetReference(), p.GetNumber(), p.GetNetname(), xy(p.GetPosition()), xy(p.GetSize()), xy(p.GetDrillSize()), p.GetShape(), p.GetAttribute(), p.GetOrientationDegrees(), list(p.GetLayerSet().Seq())])
    tracks = []
    for t in board.GetTracks():
        width = t.GetWidth(t.TopLayer()) if isinstance(t, pcbnew.PCB_VIA) else t.GetWidth()
        item = [t.m_Uuid.AsString(), t.GetClass(), t.GetNetname(), xy(t.GetStart()), xy(t.GetEnd()), width, t.GetLayer(), t.IsLocked()]
        if isinstance(t, pcbnew.PCB_VIA):
            item += [t.GetDrillValue(), t.TopLayer(), t.BottomLayer(), t.GetViaType()]
        tracks.append(item)
    zones = []
    for z in board.Zones():
        poly = z.Outline()
        outlines = []
        for i in range(poly.OutlineCount()):
            chain = poly.COutline(i)
            outlines.append([xy(chain.CPoint(j)) for j in range(chain.PointCount())])
        zones.append([z.m_Uuid.AsString(), z.GetNetname(), list(z.GetLayerSet().Seq()), outlines, z.GetLocalClearance(), z.GetThermalReliefGap(), z.GetThermalReliefSpokeWidth()])
    return {'footprints': sorted(fps), 'pads': sorted(pads), 'tracks': sorted(tracks), 'zones': sorted(zones), 'nets': sorted(n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values()), 'copper_layers': board.GetCopperLayerCount(), 'enabled_layers': [(i, board.GetLayerName(i)) for i in board.GetEnabledLayers().Seq()]}

def main():
    original = (SOURCE / BOARD).read_bytes()
    result, details = convert(original.decode())
    if DEST.exists():
        assert (DEST / BOARD).read_text() == result, 'Existing destination differs; refusing overwrite'
    else:
        shutil.copytree(SOURCE, DEST)
        (DEST / BOARD).write_text(result)
    before = snapshot(pcbnew.LoadBoard(str(SOURCE / BOARD)))
    after = snapshot(pcbnew.LoadBoard(str(DEST / BOARD)))
    assert before == after, 'KiCad parsed electrical/geometry snapshots differ'
    assert original == (SOURCE / BOARD).read_bytes(), 'Source changed'
    untouched = []
    for path in SOURCE.rglob('*'):
        if path.is_file() and path.name != BOARD:
            assert path.read_bytes() == (DEST / path.relative_to(SOURCE)).read_bytes()
            untouched.append(str(path.relative_to(SOURCE)))
    with zipfile.ZipFile(BASE / 'compat.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(DEST.rglob('*')):
            if path.is_file():
                z.write(path, path.relative_to(DEST))
        assert z.testzip() is None
    report = {'source_sha256': hashlib.sha256(original).hexdigest(), 'compat_sha256': hashlib.sha256(result.encode()).hexdigest(), 'pcbnew_semantic_equality': True, 'version_and_layers_unchanged': True, 'footprints': len(before['footprints']), 'pads': len(before['pads']), 'tracks': dict(collections.Counter(t[1] for t in before['tracks'])), 'zones': len(before['zones']), 'copper_layers': before['copper_layers'], 'other_files_identical': len(untouched), **details}
    (BASE / 'compat-validation.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
