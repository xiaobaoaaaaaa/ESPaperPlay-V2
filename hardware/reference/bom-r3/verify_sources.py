#!/usr/bin/env python3
"""Verify original manufacturer PDF bytes in staged or installed r3 archive."""
from pathlib import Path
import hashlib,json,sys
here=Path(__file__).resolve().parent
repo=here.parents[2]
data=json.loads((here/'sources.json').read_text())
assert not data['validation_issues'],data['validation_issues']
errors=[]; count=0; file_hashes={}
for s in data['sources']:
 if s['origin_domain']['classification']=='UNVERIFIED':errors.append(f"Unverified domain: {s['urls']}")
 if not s['local_files']:
  assert 'sha256' not in s and 'size_bytes' not in s,'Online-only entry must not claim file hash/size'
  continue
 for f in s['local_files']:
  p=here/f['archive_relative_path'] if f['storage']=='new_archived_pdf' else repo/f['local_path']
  if not p.is_file():errors.append(f'Missing {p}');continue
  b=p.read_bytes();h=hashlib.sha256(b).hexdigest()
  if not b.startswith(b'%PDF-'):errors.append(f'Not PDF: {p}')
  if len(b)!=f['size_bytes'] or h!=f['sha256']:errors.append(f'Hash/size mismatch: {p}')
  file_hashes[str(p)]=h;count+=1
actual={str(p.relative_to(here)) for p in (here/'files').glob('*.pdf')}
expected={f['archive_relative_path'] for f in data['prepared_files']}
if actual!=expected:errors.append(f'Archive inventory mismatch: {actual^expected}')
if len({f['sha256'] for f in data['prepared_files']})!=len(expected):errors.append('Duplicate archived SHA256')
result={'status':'FAIL' if errors else 'PASS','source_records':len(data['sources']),'pdf_references_checked':count,'unique_local_pdf_paths':len(file_hashes),'new_unique_pdfs':len(expected),'online_only_records':sum(not s['local_files'] for s in data['sources']),'errors':errors}
print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(bool(errors))
