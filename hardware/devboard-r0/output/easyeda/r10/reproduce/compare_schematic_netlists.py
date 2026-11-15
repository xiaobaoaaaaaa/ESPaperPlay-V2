#!/usr/bin/env python3
"""Compare connectivity by component-pin membership, allowing renamed nets.
An empty imported net is an isolated pin, not a connection to all other empties.
"""
import argparse,collections,json,pathlib,xml.etree.ElementTree as E
p=argparse.ArgumentParser();p.add_argument('source_xml',type=pathlib.Path);p.add_argument('imported_json',type=pathlib.Path);p.add_argument('--report',type=pathlib.Path);a=p.parse_args()
x=E.parse(a.source_xml);d=json.loads(a.imported_json.read_text())
if 'result' in d:d=json.loads(d['result']['text'])
ks={n.attrib['name']:{(p.attrib['ref'],p.attrib['pin'])for p in n}for n in x.findall('nets/net')}
krefs={c.attrib['ref']for c in x.findall('components/comp')}
es=collections.defaultdict(set);erefs=set()
for c in d['components'].values():
 ref=c['props']['Designator'];erefs.add(ref)
 for v in c.get('pinInfoMap',{}).values():
  pin=(ref,v['number']);name=v.get('net','') or '__ISOLATED__'+ref+':'+v['number'];es[name].add(pin)
kpin={p:n for n,pins in ks.items()for p in pins};epin={p:n for n,pins in es.items()for p in pins}
kg={frozenset(v) for v in ks.values()};eg={frozenset(v)for v in es.values()}
merges=[];splits=[]
for n,pins in es.items():
 others=collections.Counter(kpin[p]for p in pins if p in kpin)
 if len(others)>1:merges.append({'imported_net':n,'source_nets':dict(others)})
for n,pins in ks.items():
 others=collections.Counter(epin[p]for p in pins if p in epin)
 if len(others)>1:splits.append({'source_net':n,'imported_nets':dict(others)})
r={'source':str(a.source_xml),'imported':str(a.imported_json),'source_components':len(krefs),'imported_components':len(erefs),'source_pins':len(kpin),'imported_pins':len(epin),'source_net_groups':len(kg),'imported_net_groups':len(eg),'missing_refs':sorted(krefs-erefs),'extra_refs':sorted(erefs-krefs),'missing_pins':sorted(set(kpin)-set(epin)),'extra_pins':sorted(set(epin)-set(kpin)),'merged_nets':merges,'split_nets':splits,'connectivity_equivalent':kg==eg and krefs==erefs}
if a.report:a.report.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(r,ensure_ascii=False,indent=2))
