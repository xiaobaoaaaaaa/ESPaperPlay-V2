#!/usr/bin/env python3
"""Read back exported epro2; assert PCB geometry and repaired library state persisted."""
import argparse, collections, hashlib, json, zipfile
from pathlib import Path

def rows(text):
    for line in text.splitlines():
        if not line.strip():
            continue
        h, v = line.split('||', 1)
        v = v[:-1] if v.endswith('|') else v
        yield json.loads(h), json.loads(v) if v else None

def states(items):
    out = {}
    for h, v in items:
        key = (h['type'], h.get('id'))
        if key not in out or h.get('ticket', 0) >= out[key][0].get('ticket', 0):
            out[key] = h, v
    return {k: v for k, (h, v) in out.items() if v is not None and v != ''}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('archive', type=Path)
    ap.add_argument('--pcb-source', type=Path, required=True)
    ap.add_argument('--paste-repair', type=Path, required=True)
    ap.add_argument('--report', type=Path, required=True)
    a = ap.parse_args()
    with zipfile.ZipFile(a.archive) as z:
        assert z.testzip() is None
        text = z.read(next(n for n in z.namelist() if n.endswith('.epru'))).decode()
    docs = collections.defaultdict(list)
    current = None
    for h, v in rows(text):
        if h['type'] == 'DOCHEAD':
            current = v['docType'], v['uuid']
        docs[current].append((h, v))
    source = states(rows(a.pcb_source.read_text()))
    board = states(docs['PCB', '52caa9452ee66dee'])
    # Runtime serialization adds defaults, view state and rounded layer thickness.
    # Compare design primitives exactly; assess runtime-only state separately.
    geometry_types = {'COMPONENT', 'ATTR', 'LINE', 'VIA', 'PAD', 'POLY', 'FILL',
                      'POUR', 'POURED', 'REGION', 'NET', 'STRING', 'ARC'}
    ss = {k: v for k, v in source.items() if k[0] in geometry_types}
    bs = {k: v for k, v in board.items() if k[0] in geometry_types}
    diffs = [str(k) for k in ss.keys() | bs.keys() if ss.get(k) != bs.get(k)]
    assert not diffs, diffs[:20]
    source_pads = {k: v for k, v in source.items() if k[0] == 'PAD_NET'}
    exported_pads = {k: v for k, v in board.items() if k[0] == 'PAD_NET'}
    assert all(exported_pads.get(k) == v for k, v in source_pads.items())
    extra_pads = {k: v for k, v in exported_pads.items() if k not in source_pads}
    # Archive retains unused empty pad-net records. They must never carry a net.
    assert all(not v.get('padNet') for v in extra_pads.values())
    checked_rules = []
    for k, v in source.items():
        if k[0] == 'RULE' and json.loads(k[1])[1] != 'AUTO_ROUTER':
            assert board.get(k) == v, k
            checked_rules.append(k[1])
    assert ('FILL', 'ie510ie13') not in board
    footprint_states = {uid: states(items) for (typ, uid), items in docs.items() if typ == 'FOOTPRINT'}
    mic = footprint_states['57e376c00af9ce28']
    pads = [(k, v) for k, v in mic.items() if k[0] == 'PAD' and v.get('num') == '4']
    paste = [(k, v) for k, v in mic.items() if k[0] == 'FILL' and (k[1] == 'ie13' or str(k[1]).startswith('u803_paste_ring_sector_'))]
    assert len(pads) == len(paste) == 4
    assert all(v['defaultPad']['padType'] == 'POLYGON' and v['defaultPad']['path'].count('ARC') == 2 for k, v in pads)
    assert all(v['path'][0].count('ARC') == 2 for k, v in paste)
    repair = json.loads(a.paste_repair.read_text())
    checks = []
    for change in repair['changes']:
        pad = footprint_states[change['footprint_uuid']]['PAD', change['pad_id']]
        for key, values in change['changes'].items():
            assert pad.get(key) == values['after'], (change['ref'], key, pad.get(key))
            checks.append([change['ref'], change['pad_id'], key])
    report = {
        'status': 'PASS',
        'archive_sha256': hashlib.sha256(a.archive.read_bytes()).hexdigest(),
        'zip_integrity': 'PASS',
        'document_counts': dict(collections.Counter(typ for typ, uid in docs)),
        'pcb_saved_design_primitives_equal_to_audited_source': True,
        'compared_design_types': sorted(geometry_types),
        'active_pad_net_records_identical': len(source_pads),
        'additional_unused_empty_pad_net_records': len(extra_pads),
        'critical_rules_identical': checked_rules,
        'u803_copper_sectors': len(pads), 'u803_paste_sectors': len(paste),
        'stray_board_paste_fill_absent': True,
        'paste_suppression_properties_verified': len(checks),
        'limits': 'Archive readback, not a fresh import or exhaustive whole-board Gerber comparison.'
    }
    a.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
