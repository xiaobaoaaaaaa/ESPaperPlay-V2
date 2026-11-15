#!/usr/bin/env python3
"""Verify the frozen CAM bundle and its exact evidence/package relationships."""
import hashlib,json,zipfile
from pathlib import Path
B=Path(__file__).resolve().parents[1]
sha=lambda data:hashlib.sha256(data).hexdigest()
for row in(B/'SHA256SUMS').read_text().splitlines():
 digest,name=row.split('  ',1);assert sha((B/name).read_bytes())==digest,name
reports={p.name:json.loads(p.read_text())for p in(B/'review').glob('*.json')}
for name in ['final-netlist-audit.json','final-archive-readback.json','final-outer-cam-audit.json','final-footprint-audit.json','final-copper-pad-flash-audit.json','final-mask-flash-audit.json','final-npth-audit.json','final-u403-capsule-audit.json','final-assembly-invariant.json']:
 assert reports[name]['status']=='PASS',name
assert reports['final-drc.json']['result']['drc']==[]
assert reports['final-via-audit.json']['geometric_and_drill_audit_passed']
assert reports['final-paste-operation-invariant.json']['geometry_equal']
assert all(reports['final-silk-operation-invariant.json'][k]for k in ['geometry_equal','regions_equal','macro_definitions_equal'])
assert sha((B/'ESPaperPlay-V2-r10-CAM-final.epro2').read_bytes())==reports['final-archive-readback.json']['archive_sha256']
expected={'Gerber_TopLayer.GTL','Gerber_InnerLayer1.G1','Gerber_InnerLayer2.G2','Gerber_BottomLayer.GBL','Gerber_TopSolderMaskLayer.GTS','Gerber_BottomSolderMaskLayer.GBS','Gerber_TopSilkscreenLayer.GTO','Gerber_BottomSilkscreenLayer.GBO','Gerber_BoardOutlineLayer.GKO','Drill_PTH_Through.DRL','Drill_NPTH_Through.DRL'}
with zipfile.ZipFile(B/'Gerber-full-audit-only.zip')as full,zipfile.ZipFile(B/'ESPaperPlay-V2-r10-EasyEDA-board-REVIEW_ONLY.zip')as board:
 assert full.testzip()is None and board.testzip()is None
 assert set(board.namelist())==expected|{'README.txt','thermal-via-fill-spec.csv'}
 assert all(board.read(n)==full.read(n)for n in expected)
 assert sha(full.read('Gerber_TopPasteMaskLayer.GTP'))==reports['final-paste-assembly-summary.json']['final_paste_raw_sha256']
with zipfile.ZipFile(B/'ESPaperPlay-r10-DIY-stencil-REVIEW_ONLY.zip')as z:
 assert z.testzip()is None;names=[n for n in z.namelist()if n.lower().endswith('.gtp')];assert len(names)==1
 assert sha(z.read(names[0]))==reports['final-paste-assembly-summary.json']['dedicated_DIY_stencil_sha256']
with zipfile.ZipFile(B/'snapshots.zip')as z:
 assert z.testzip()is None
 raw=z.read('final-pcb-source.txt');fp=z.read('final-footprint-sources.json')
 assert sha(raw)in reports['final-source-changes.json']['inputs'].values()
 assert sha(fp)in reports['final-source-changes.json']['inputs'].values()
print('PASS: all bundle hashes, saved archive, report gates, exact PCB subset, dedicated stencil and source bindings.')
