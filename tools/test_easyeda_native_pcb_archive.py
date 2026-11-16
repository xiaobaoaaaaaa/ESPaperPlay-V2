#!/usr/bin/env python3
"""Self-contained archive-coherence fixtures; no CAD, API or build dependencies."""
import argparse
import copy
import hashlib
import json
import math
import tempfile
import zipfile
from pathlib import Path

import check_easyeda_native_pcb_archive as checker


def native_document(uuid, kind, records):
    lines = [json.dumps({'type': 'DOCHEAD'}) + '||' +
             json.dumps({'uuid': uuid, 'docType': kind, 'client': 'fixture'}) + '|']
    for ticket, ((record_type, ident), body) in enumerate(records.items(), 1):
        lines.append(json.dumps({'type': record_type, 'id': ident, 'ticket': ticket}) +
                     '||' + json.dumps(body) + '|')
    return '\n'.join(lines) + '\n'


def run():
    baseline = {
        ('COMPONENT', ref): {'x': n, 'y': 0, 'angle': -90,
                            'attrs': {'Designator': ref, 'Footprint': 'fp-' + ref}}
        for n, ref in enumerate(checker.FOOTPRINT_REFS)
    }
    baseline.update({
        ('LINE', 'tiny'): {'netName': 'N', 'layerId': 1, 'startX': 0,
                          'startY': 0, 'endX': .001, 'endY': 0, 'width': 5.9055},
        ('POUR', 'ground'): {'netName': 'GND', 'layerId': 15,
                             'path': [0, 0, 'L', 1, 0, 1, 1, 0, 1]},
        ('POURED', '["POURED","ground"]'): {'pourFill': [{'id': 'fill-1', 'fill': True, 'strokeWidth': 0, 'path': [[10, 20, 'ARC', 90, 30, 40, 'L', 50, 60]]}]},
    })
    cases = []
    with tempfile.TemporaryDirectory(prefix='native-archive-self-test-') as name:
        directory = Path(name)
        footprints = directory / 'source' / 'footprints'
        footprints.mkdir(parents=True)
        footprint_logs = []
        for ref in checker.FOOTPRINT_REFS:
            text = native_document('fp-' + ref, 'FOOTPRINT', {
                ('PAD', 'pad'): {'number': '1', 'x': 0, 'y': 0},
            })
            (footprints / (ref + '.efoo')).write_text(text)
            footprint_logs.append(text)

        def check(title, mutate, fail, mutate_source=None):
            source = copy.deepcopy(baseline)
            archive = copy.deepcopy(baseline)
            if mutate_source:
                mutate_source(source)
            mutate(archive)
            (directory / 'source' / 'PCB-layout.epcb').write_text(
                native_document('board', 'PCB', source))
            path = directory / 'fixture.epro2'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('fixture.epru', native_document('board', 'PCB', archive) +
                           ''.join(footprint_logs))
            result = checker.check(directory, path)
            passed = (result['status'] == 'FAIL') == fail
            cases.append({'name': title, 'pass': passed,
                          'expected_failure': fail, 'actual_status': result['status'],
                          'error_scopes': [e['scope'] for e in result['errors']]})

        cache_key = ('POURED', '["POURED","ground"]')
        component_key = ('COMPONENT', checker.FOOTPRINT_REFS[0])
        check('Exact geometry and associated derived-cache records match', lambda d: None, False)
        check('Snapshots before repour may both omit derived-cache records',
              lambda d: d.pop(cache_key), False, lambda d: d.pop(cache_key))
        check('Changed computed-cache payload remains a reported mismatch',
              lambda d: d[cache_key].update(pourFill=[{'fill': True, 'path': []}]), True)
        check('An orphan derived cache cannot reference a missing POUR',
              lambda d: d.update({('POURED', '["POURED","missing"]'): {'pourFill': []}}), True)
        check('A cache missing from only one side is not silently discarded',
              lambda d: d.pop(cache_key), True)
        check('POUR network definitions remain exact',
              lambda d: d['POUR', 'ground'].update(netName='WRONG'), True)
        check('POUR boundary coordinates remain exact',
              lambda d: d['POUR', 'ground']['path'].__setitem__(0, .001), True)
        check('No component-angle normalizer is introduced',
              lambda d: d[component_key].update(angle=270), True)
        check('A 0.001-degree component change fails',
              lambda d: d[component_key].update(angle=-89.999), True)
        check('A 0.001-unit component coordinate change fails',
              lambda d: d[component_key].update(x=.001), True)
        check('Component attribute changes fail',
              lambda d: d[component_key]['attrs'].update(ReviewMarker='changed'), True)
        check('An extra microscopic LINE is still a real record mismatch',
              lambda d: d.update({('LINE', 'extra'): copy.deepcopy(d['LINE', 'tiny'])}), True)
        check('A missing microscopic LINE remains a mismatch',
              lambda d: d.pop(('LINE', 'tiny')), True)
        check('A 0.001-unit LINE endpoint change fails',
              lambda d: d['LINE', 'tiny'].update(endX=.002), True)
        check('A LINE network change fails',
              lambda d: d['LINE', 'tiny'].update(netName='WRONG'), True)
        check('Unknown cache-like record types remain unclassified failures',
              lambda d: d.update({('POURED_UNKNOWN', 'x'): {}}), True)

        def token_change(d, token, value):
            d[cache_key]['pourFill'][0]['path'][0][token] = value

        check('One ULP derived-cache coordinate difference is explicitly reported',
              lambda d: token_change(d, 0, math.nextafter(10.0, math.inf)), False)
        check('Tiny derived-cache ARC angle representation difference is explicitly reported',
              lambda d: token_change(d, 3, 90 + 2e-12), False)
        check('Two ULP cache coordinate change is rejected',
              lambda d: token_change(d, 0, math.nextafter(math.nextafter(10.0, math.inf), math.inf)), True)
        check('A 1e-9 mil cache coordinate change is rejected',
              lambda d: token_change(d, 0, 10 + 1e-9), True)
        check('A 0.001-degree cache ARC change is rejected',
              lambda d: token_change(d, 3, 90.001), True)
        check('Cache stroke width remains exact',
              lambda d: d[cache_key]['pourFill'][0].update(strokeWidth=1e-15), True)
        check('Cache fill IDs remain exact',
              lambda d: d[cache_key]['pourFill'][0].update(id='different-fill-id'), True)
        check('Cache path command changes remain exact',
              lambda d: token_change(d, 2, 'UNKNOWN'), True)
        check('Cache fill presence remains exact',
              lambda d: d[cache_key]['pourFill'][0].update(fill=False), True)
        check('Authored POUR coordinate one ULP change still fails',
              lambda d: d['POUR', 'ground']['path'].__setitem__(3, math.nextafter(1.0, math.inf)), True)

    return {
        'status': 'PASS_ARCHIVE_COHERENCE_SELF_TESTS' if all(c['pass'] for c in cases) else 'FAIL',
        'count': len(cases), 'cases': cases,
        'checker_sha256': hashlib.sha256(Path(checker.__file__).read_bytes()).hexdigest(),
        'scope': 'Synthetic native-record and archive comparison only; not PCB geometry, DRC or CAM validation.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end='')
    return int(report['status'] != 'PASS_ARCHIVE_COHERENCE_SELF_TESTS')


if __name__ == '__main__':
    raise SystemExit(main())
