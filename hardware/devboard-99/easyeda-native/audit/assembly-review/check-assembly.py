#!/usr/bin/env python3
"""Check the approved stencil delta and orientation against a native CAM export."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
NATIVE = HERE.parent.parent
sys.path.insert(0, str(NATIVE / 'verification'))
from native_cam_geometry import GerberFile, MM, object_geometry
from native_source_geometry import load_inputs
from shapely.geometry import box
from shapely.strtree import STRtree


def fingerprint(layer):
    """Hash the ordered physical Gerber primitives, including draw polarity."""
    digest = hashlib.sha256()
    for obj in layer.objects:
        primitives = [repr(p) for p in obj.to_primitives(MM)]
        data = json.dumps([obj.polarity_dark, primitives]).encode('ascii')
        digest.update(len(data).to_bytes(8, 'big'))
        digest.update(data)
    return digest.hexdigest()


def read_layer(archive, suffix):
    name, = [n for n in archive.namelist() if n.endswith(suffix)]
    return GerberFile.from_string(archive.read(name).decode('ascii'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cam', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args()
    report = json.loads((HERE / 'stencil-review.json').read_text())
    orientation = HERE / 'top-orientation.svg'
    if hashlib.sha256(orientation.read_bytes()).hexdigest() != report['orientation_svg_sha256']:
        raise ValueError('Assembly orientation drawing changed')
    with ZipFile(args.cam) as bundle:
        layers = {ext: read_layer(bundle, ext) for ext in ('.GTL', '.GTP')}
    for ext, layer in layers.items():
        if fingerprint(layer) != report['physical_layers'][ext]['ordered_primitive_sha256']:
            raise ValueError(f'{ext} physical geometry differs from reviewed artwork')

    source, state, pads, *_ = load_inputs(args)
    sorted_state = sorted(state, key=lambda part: part['ref'])
    state_bytes = json.dumps(sorted_state, sort_keys=True, separators=(',', ':')).encode()
    if hashlib.sha256(state_bytes).hexdigest() != report['placement_and_pin_sha256']:
        raise ValueError('Component/pad state differs from the reviewed orientation map')
    dnp = {p['ref'] for p in state if source['COMPONENT', p['id']]['attrs']['DNP'] == 'true'}
    if dnp != set(report['DNP_refs']):
        raise ValueError('DNP population changed')
    omit = dnp | set(report['hand_solder_refs'])
    changes = {(p['ref'], p['pin']): p['aperture_bounds_mm'] for p in report['adjusted_openings']}
    tree = STRtree([p['g'] for p in pads])
    removed = Counter()
    used_changes = set()
    expected = []
    for obj in layers['.GTP'].objects:
        if not obj.polarity_dark:
            raise ValueError('Unexpected clear opening in source stencil')
        g = object_geometry(obj)
        overlaps = [(pads[i]['g'].intersection(g).area, i) for i in tree.query(g)]
        hits = [(area, i) for area, i in overlaps if area > 1e-7]
        if not hits or len({pads[i]['ref'] in omit for _, i in hits}) != 1:
            raise ValueError(f'Unassigned or mixed hand-solder/reflow opening at {g.bounds}')
        _, i = max(hits)
        ref, pin = pads[i]['ref'], pads[i]['pin']
        if ref in omit:
            removed[ref] += 1
        elif (ref, pin) in changes:
            if (ref, pin) in used_changes:
                raise ValueError(f'Duplicate input opening at {ref}.{pin}')
            used_changes.add((ref, pin))
            expected.append(box(*changes[ref, pin]))
        else:
            expected.append(g)
    if dict(removed) != report['removed_openings_by_ref'] or used_changes != set(changes):
        raise ValueError('Reviewed deletion or adjustment did not match original apertures')
    stencil_path = HERE / 'native99-first-two-top-paste-review.GTP'
    actual = GerberFile.from_string(stencil_path.read_text()).objects
    for number, (want, obj) in enumerate(zip(expected, actual, strict=True), 1):
        if not obj.polarity_dark or not want.equals(object_geometry(obj)):
            raise ValueError(f'Stencil shape/polarity differs at opening {number}')
    print(f'PASS · {len(state)} placements/pad states · {len(actual)} openings · {sum(removed.values())} omitted · {len(used_changes)} adjusted')


if __name__ == '__main__':
    main()
