#!/usr/bin/env python3
"""Check r5 additions against a frozen r4 snapshot and native KiCad pads.

The pin contract is maintained independently of the drawing script. This is a
connectivity/metadata check, not an analog simulation or manufacturing release.
"""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('netlist', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    basefile = PROJECT / 'review-r5/electrical-baseline-r4.json'
    contractfile = PROJECT / 'review-r5/allowed-r4-r5-delta.json'
    bomfile = PROJECT / 'review-r5/bom-review.json'
    base = json.loads(basefile.read_text())
    contract = json.loads(contractfile.read_text())
    bom = json.loads(bomfile.read_text())
    root = ET.parse(args.netlist).getroot()
    comps = {c.attrib['ref']: c for c in root.findall('./components/comp')}
    rows = {c['ref']: c for c in bom['items']}
    pins = {}
    for net in root.findall('./nets/net'):
        for node in net.findall('node'):
            key = node.attrib['ref'] + '.' + node.attrib['pin']
            assert key not in pins, ('duplicate pin', key)
            pins[key] = net.attrib['name']
    assert set(comps) == set(rows) == set(base['components']) | set(contract['added_components'])
    assert set(contract['pin_changes']) <= set(base['pins'])
    expected_pins = dict(base['pins'])
    for key, change in contract['pin_changes'].items():
        assert expected_pins[key] == change['before'], (key, 'baseline mismatch')
        expected_pins[key] = change['after']
    for ref, mapping in contract['added_components'].items():
        assert ref not in base['components']
        for pin, net in mapping.items():
            expected_pins[ref + '.' + pin] = net
    assert set(pins) == set(expected_pins), ('pin inventory changed', set(pins) ^ set(expected_pins))
    for key, expected in expected_pins.items():
        assert pins[key] == expected, (key, pins[key], expected)
    libpins = {(x.attrib['lib'], x.attrib['part']): {v.attrib['num'] for v in x.findall('./pins/pin')}
               for x in root.findall('./libparts/libpart')}
    import pcbnew
    cache = {}
    dnps = []
    for ref, c in comps.items():
        row = rows[ref]
        actual = {
            'value': c.findtext('value'), 'footprint': c.findtext('footprint'),
            'uuid': c.findtext('tstamps'), 'dnp': c.find("property[@name='dnp']") is not None,
            'mpn': c.findtext("fields/field[@name='Candidate_MPN']", ''),
            'manufacturer': c.findtext("fields/field[@name='Manufacturer']", ''),
        }
        for key in ('value', 'footprint', 'dnp', 'mpn', 'manufacturer'):
            assert actual[key] == row[key], (ref, key, actual[key], row[key])
        if ref in base['components']:
            expected = dict(base['components'][ref])
            for key, change in contract['component_changes'].get(ref, {}).items():
                assert expected[key] == change['before'], (ref, key, 'baseline mismatch')
                expected[key] = change['after']
            assert actual == expected, (ref, 'undeclared component change', actual, expected)
        if actual['dnp']:
            dnps.append(ref)
        fp = actual['footprint']
        assert fp, (ref, 'missing footprint')
        if fp not in cache:
            lib, name = fp.split(':', 1)
            folder = PROJECT / 'ESPaperPlay.pretty' if lib == 'ESPaperPlay' else Path('/usr/share/kicad/footprints') / (lib + '.pretty')
            native = pcbnew.FootprintLoad(str(folder), name)
            assert native is not None, fp
            pads = []
            for pad in native.Pads():
                if pad.GetNumber():
                    pads.append({'number': pad.GetNumber(),
                                 'position_mm': [pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)],
                                 'size_mm': [pcbnew.ToMM(pad.GetSize().x), pcbnew.ToMM(pad.GetSize().y)]})
            cache[fp] = {'path': str(folder / (name + '.kicad_mod')),
                         'sha256': digest(folder / (name + '.kicad_mod')), 'pads': pads, 'refs': []}
        cache[fp]['refs'].append(ref)
        lib = c.find('libsource')
        symbolpins = libpins[(lib.attrib['lib'], lib.attrib['part'])]
        assert {x['number'] for x in cache[fp]['pads']} == symbolpins, (ref, 'pad numbers differ from symbol')
        assert set(row['pins']) == symbolpins, (ref, 'BOM pin inventory')
    assert set(dnps) == {'R108', 'J301', 'J302', 'J303', 'C501', 'C502'}
    # Independent check against TI D0008A drawing 4214825/C, not just pad IDs.
    u901pads = {x['number']: x for x in cache['ESPaperPlay:TI_D0008A_SOIC8']['pads']}
    expected_xy = {'1': (-2.7, -1.905), '2': (-2.7, -0.635),
                   '3': (-2.7, 0.635), '4': (-2.7, 1.905),
                   '5': (2.7, 1.905), '6': (2.7, 0.635),
                   '7': (2.7, -0.635), '8': (2.7, -1.905)}
    for pin, xy in expected_xy.items():
        pad = u901pads[pin]
        assert all(abs(a - b) < 1e-6 for a, b in zip(pad['position_mm'], xy)), ('U901 pad position', pin)
        assert all(abs(a - b) < 1e-6 for a, b in zip(pad['size_mm'], (1.55, 0.6))), ('U901 pad size', pin)
    result = {'status': 'PASS', 'revision': 'r5', 'positions': len(comps),
              'nets': len(root.findall('./nets/net')), 'all_pin_connections_checked': len(pins),
              'dnp': sorted(dnps), 'old_component_uuid_and_dnp_preserved': True,
              'unchanged_r4_connections_preserved': True, 'added_components': sorted(contract['added_components']),
              'footprint_positions_checked': len(comps), 'unique_footprints_checked': len(cache),
              'U901_TI_D0008A_pad_geometry_checked': True,
              'footprints': cache,
              'inputs': {str(f.relative_to(PROJECT)) if f.is_relative_to(PROJECT) else str(f): digest(f)
                         for f in (basefile, contractfile, bomfile, args.netlist)},
              'scope': 'Exact old/new pin contract, UUID/DNP/BOM and native numbered pads; no analog, layout, mechanical or power-on qualification.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('footprints', 'inputs')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
