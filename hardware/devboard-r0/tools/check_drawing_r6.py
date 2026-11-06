#!/usr/bin/env python3
"""Verify that a schematic redraw preserves the frozen r5 electrical design.

Uses only the exported XML, native project files, and the committed JSON baseline.
It deliberately does not import the drawing helper or any old schematic generator.
Native S-expression fingerprints ignore formatting whitespace, not symbol content.
This checks equivalence; it is not ERC, analog simulation, PCB or assembly review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
BASELINE = PROJECT / 'review-r6/electrical-baseline-r5.json'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def parse_native(path: Path):
    """Small independent S-expression reader; quoted contents stay exact."""
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', path.read_text())
    stack = []
    roots = []
    for token in tokens:
        if token == '(':
            node = []
            if stack:
                stack[-1].append(node)
            else:
                roots.append(node)
            stack.append(node)
        elif token == ')':
            assert stack, ('unmatched closing parenthesis', str(path))
            stack.pop()
        else:
            assert stack, ('token outside expression', str(path), token)
            stack[-1].append(token)
    assert not stack and len(roots) == 1, ('invalid native root', str(path))
    return roots[0]


def literal(atom: str) -> str:
    return json.loads(atom) if atom.startswith('"') else atom


def children(node, name):
    return [child for child in node[1:] if isinstance(child, list) and child[0] == name]


def one(node, name, required=True):
    found = children(node, name)
    assert len(found) <= 1, ('duplicate child', name)
    if required:
        assert found, ('missing child', name)
    return found[0] if found else None


def value(node, name, default=None):
    child = one(node, name, required=False)
    return literal(child[1]) if child else default


def xml_canonical(element):
    """XML ordering/indentation is immaterial; all attributes and values remain."""
    descendants = [xml_canonical(child) for child in element]
    descendants.sort(key=lambda child: json.dumps(child, ensure_ascii=False, sort_keys=True))
    return {'tag': element.tag, 'attributes': dict(element.attrib),
            'text': (element.text or '').strip(), 'children': descendants}


def netlist_snapshot(path: Path):
    root = ET.parse(path).getroot()
    components = {}
    for comp in root.findall('./components/comp'):
        ref = comp.attrib['ref']
        assert ref not in components, ('duplicate XML component', ref)
        fields = {}
        for field in comp.findall('./fields/field'):
            name = field.attrib['name']
            assert name not in fields, ('duplicate component field', ref, name)
            fields[name] = field.text or ''
        components[ref] = {
            'value': comp.findtext('value', ''),
            'footprint': comp.findtext('footprint', ''),
            'uuid': comp.findtext('tstamps', ''),
            'dnp': comp.find("property[@name='dnp']") is not None,
            'fields': fields,
            'sheetpath': dict(comp.find('sheetpath').attrib),
            # Includes libsource, properties, units and every other XML field.
            'all_component_metadata_sha256': fingerprint(xml_canonical(comp)),
        }
    pins = {}
    nets = {}
    for net in root.findall('./nets/net'):
        name = net.attrib['name']
        assert name not in nets, ('duplicate named net', name)
        members = []
        for node in net.findall('node'):
            key = node.attrib['ref'] + '.' + node.attrib['pin']
            assert key not in pins, ('pin on multiple nets', key)
            assert node.attrib['ref'] in components, ('unknown component', key)
            attributes = {k: v for k, v in node.attrib.items() if k not in ('ref', 'pin')}
            pins[key] = {'net': name, 'attributes': attributes}
            members.append(key)
        nets[name] = {'members': sorted(members),
                      'attributes': {k: v for k, v in net.attrib.items() if k not in ('name', 'code')}}
    nc = {key: data for key, data in pins.items()
          if 'no_connect' in data['attributes'].get('pintype', '') or data['net'].startswith('unconnected-')}
    return {'components': components, 'pins': pins, 'nets': nets, 'no_connect_pins': nc}


def native_snapshot(directory: Path):
    pages = {}
    counts = {'wire': 0, 'label': 0, 'global_label': 0, 'junction': 0, 'no_connect': 0}
    seen_refs = set()
    for path in sorted(directory.glob('*.kicad_sch')):
        tree = parse_native(path)
        assert tree[0] == 'kicad_sch', path
        libsec = one(tree, 'lib_symbols')
        library_symbols = {}
        for symbol in children(libsec, 'symbol'):
            name = literal(symbol[1])
            assert name not in library_symbols, ('duplicate embedded definition', path.name, name)
            library_symbols[name] = fingerprint(symbol)
        components = {}
        for symbol in children(tree, 'symbol'):
            properties = {}
            for field in children(symbol, 'property'):
                name = literal(field[1])
                assert name not in properties, ('duplicate native property', path.name, name)
                properties[name] = literal(field[2])
            ref = properties['Reference']
            assert ref not in seen_refs, ('duplicate native reference', ref)
            seen_refs.add(ref)
            pins = {}
            for pin in children(symbol, 'pin'):
                number = literal(pin[1])
                assert number not in pins, ('duplicate native pin identity', ref, number)
                pins[number] = value(pin, 'uuid')
            # Instance position, rotation, mirroring and property display effects
            # are visual. All semantic scalar attributes and instance paths stay.
            semantics = [child for child in symbol[1:] if isinstance(child, list)
                         and child[0] not in ('at', 'mirror', 'property', 'pin', 'fields_autoplaced')]
            semantics.sort(key=lambda child: json.dumps(child, ensure_ascii=False))
            components[ref] = {'uuid': value(symbol, 'uuid'), 'pin_uuids': pins,
                               'lib_id': value(symbol, 'lib_id'), 'unit': value(symbol, 'unit'),
                               'properties': properties,
                               'nonvisual_instance_sha256': fingerprint(semantics)}
        sheets = {}
        for sheet in children(tree, 'sheet'):
            uid = value(sheet, 'uuid')
            assert uid not in sheets
            props = {literal(field[1]): literal(field[2]) for field in children(sheet, 'property')}
            sheets[uid] = {'properties': props,
                           'instances_sha256': fingerprint(one(sheet, 'instances', required=False)),
                           'pins_sha256': fingerprint(children(sheet, 'pin'))}
        pages[path.name] = {'uuid': value(tree, 'uuid'), 'library_symbols': library_symbols,
                            'components': components, 'child_sheets': sheets}
        for kind in counts:
            counts[kind] += len(children(tree, kind))
    library_path = directory / 'ESPaperPlay.kicad_sym'
    assert library_path.is_file(), library_path
    library = parse_native(library_path)
    return {'pages': pages,
            'local_symbol_definitions': {literal(symbol[1]): fingerprint(symbol)
                                         for symbol in children(library, 'symbol')},
            'drawing_counts': counts}


def equal(actual, expected, description):
    if actual == expected:
        return
    if isinstance(actual, dict) and isinstance(expected, dict):
        missing = sorted(set(expected) - set(actual))
        added = sorted(set(actual) - set(expected))
        changed = sorted(key for key in set(expected) & set(actual) if actual[key] != expected[key])
        raise AssertionError(f'{description}: missing={missing[:10]}, added={added[:10]}, changed={changed[:10]}')
    raise AssertionError(f'{description} differs from r5')


def verify(baseline, actual_xml, actual_native):
    assert baseline['schema_version'] == 1
    for key in ('components', 'pins', 'nets', 'no_connect_pins'):
        equal(actual_xml[key], baseline['netlist'][key], 'XML ' + key)
    equal(set(actual_native['pages']), set(baseline['native']['pages']), 'native sheet inventory')
    for name, expected in baseline['native']['pages'].items():
        actual = actual_native['pages'][name]
        equal(actual['uuid'], expected['uuid'], name + ' sheet UUID')
        equal(actual['components'], expected['components'], name + ' component/pin UUIDs and metadata')
        equal(actual['library_symbols'], expected['library_symbols'], name + ' embedded symbol definitions')
        equal(actual['child_sheets'], expected['child_sheets'], name + ' hierarchy')
    equal(actual_native['local_symbol_definitions'], baseline['native']['local_symbol_definitions'],
          'local symbol library definitions')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('netlist', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(BASELINE.read_text())
    actual_xml = netlist_snapshot(args.netlist)
    actual_native = native_snapshot(PROJECT)
    verify(baseline, actual_xml, actual_native)
    instances = [item for page in actual_native['pages'].values() for item in page['components'].values()]
    result = {
        'status': 'PASS', 'revision': 'r6 DRAWING', 'electrical_baseline': 'r5',
        'components': len(actual_xml['components']), 'nets': len(actual_xml['nets']),
        'all_pin_connections_checked': len(actual_xml['pins']),
        'no_connect_pins_preserved': len(actual_xml['no_connect_pins']),
        'native_sheets_checked': len(actual_native['pages']),
        'native_component_uuids_checked_including_flags': len(instances),
        'native_pin_uuids_checked_including_flags': sum(len(item['pin_uuids']) for item in instances),
        'embedded_symbol_definitions_checked': sum(len(p['library_symbols']) for p in actual_native['pages'].values()),
        'local_symbol_definitions_checked': len(actual_native['local_symbol_definitions']),
        'all_xml_component_fields_and_sheetpaths_preserved': True,
        'exact_named_nets_membership_pin_functions_types_and_nc_preserved': True,
        'component_and_pin_uuids_preserved': True,
        'native_symbol_definitions_preserved': True,
        'drawing_counts_before': baseline['native']['drawing_counts'],
        'drawing_counts_after': actual_native['drawing_counts'],
        'inputs': {'baseline': {'path': str(BASELINE.relative_to(PROJECT)), 'sha256': digest(BASELINE)},
                   'netlist': {'path': str(args.netlist), 'sha256': digest(args.netlist)},
                   'native_sources': {path.name: digest(path)
                                      for path in sorted(PROJECT.glob('*.kicad_sch'))},
                   'local_symbol_library_sha256': digest(PROJECT / 'ESPaperPlay.kicad_sym')},
        'scope': 'Pure drawing equivalence only. Coordinates, rotation/mirroring, annotation layout, wires, labels, junctions, title dates/revision and module graphics may change. All r5 electrical metadata and named connectivity must remain identical; no ERC, analog, PCB or hardware qualification claim.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: val for key, val in result.items() if key not in ('inputs', 'scope')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
