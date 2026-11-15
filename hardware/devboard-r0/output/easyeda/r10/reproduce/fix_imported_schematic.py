#!/usr/bin/env python3
"""Repair two verified KiCad -> EasyEDA hierarchy translation errors in a copy.

Requires all type-19 instances to match KiCad global_label names on every page.
Refuses actual hierarchical labels, duplicate document blocks, and overwriting.
Leaves PCB/library geometry intact; removes ERC-only power:PWR_FLAG instances.
"""
import argparse, collections, hashlib, json, pathlib, re, zipfile

def sexp(text):
    toks=re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text)
    stack=[]; root=None
    for t in toks:
        if t=='(':
            a=[]
            if stack:stack[-1].append(a)
            else:root=a
            stack.append(a)
        elif t==')':stack.pop()
        else:stack[-1].append(json.loads(t) if t.startswith('"') else t)
    assert not stack
    return root

def children(node,tag):return [n for n in node if isinstance(n,list) and n and n[0]==tag]
def one(node,tag):
    a=children(node,tag);return a[0] if a else None

def parse_docs(text):
    docs=[]; seen=set()
    for line in text.splitlines():
        if not line.strip():continue
        a,b=line.split('||',1);h=json.loads(a);v=json.loads(b.rstrip('|'))
        if h['type']=='DOCHEAD':
            assert v['uuid'] not in seen,'Duplicate document blocks require merge before patch'
            seen.add(v['uuid']);cur={'header':(h,v),'records':[]};docs.append(cur)
        else:cur['records'].append((h,v))
    return docs

def meta(d):
    return [v for h,v in d['records'] if h['type']=='META'][-1]

def main():
    p=argparse.ArgumentParser();p.add_argument('input',type=pathlib.Path);p.add_argument('output',type=pathlib.Path);p.add_argument('--source',type=pathlib.Path,required=True);a=p.parse_args()
    assert a.input.resolve()!=a.output.resolve() and not a.output.exists(),'Refuse overwrite'
    src={}
    for f in a.source.glob('*.kicad_sch'):
        s=sexp(f.read_text());assert not children(s,'hierarchical_label'),f'Actual hierarchy labels present: {f}'
        flags=[]
        for sy in children(s,'symbol'):
            if one(sy,'lib_id')==['lib_id','power:PWR_FLAG']:
                flags.append(next(x[2] for x in children(sy,'property') if x[1]=='Reference'))
        src[f.stem]={'globals':collections.Counter(x[1] for x in children(s,'global_label')),'flags':set(flags)}
    with zipfile.ZipFile(a.input) as z:
        entry=next(n for n in z.namelist() if n.endswith('.epru'));text=z.read(entry).decode();docs=parse_docs(text)
        symbols={d['header'][1]['uuid']:d for d in docs if d['header'][1]['docType']=='SYMBOL'}
        netports={u for u,d in symbols.items() if meta(d).get('docType')==19}
        flagsyms={u for u,d in symbols.items() if meta(d).get('title')=='power_PWR_FLAG'}
        assert flagsyms, 'PWR_FLAG library not found'
        report={'input':str(a.input),'input_sha256':hashlib.sha256(a.input.read_bytes()).hexdigest(),'pages':[],'patched_symbol_uuids':[],'pcb_unchanged':True}
        removed={};used_ports=set();seen_pages=set()
        for d in docs:
            if d['header'][1]['docType']!='SCH_PAGE':continue
            title=meta(d)['title'];seen_pages.add(title);assert title in src,title
            attrs=collections.defaultdict(dict)
            for h,v in d['records']:
                if h['type']=='ATTR' and isinstance(v,dict):attrs[v['parentId']][v['key']]=v['value']
            actual_globals=collections.Counter();remove=set();actual_flags=set()
            for h,v in d['records']:
                if h['type']!='COMPONENT' or not isinstance(v,dict):continue
                at=attrs[h['id']]
                if at.get('Symbol') in netports:
                    actual_globals[at.get('Name')]+=1;used_ports.add(at['Symbol'])
                if at.get('Symbol') in flagsyms:
                    remove.add(h['id']);actual_flags.add(at.get('Designator'))
            assert actual_globals==src[title]['globals'],f'Global label instance mismatch on {title}: {actual_globals-src[title]["globals"]} / {src[title]["globals"]-actual_globals}'
            assert actual_flags==src[title]['flags'],f'PWR_FLAG references mismatch on {title}'
            removed[d['header'][1]['uuid']]=remove
            stale_net_attrs=[h['id'] for h,v in d['records'] if h['type']=='ATTR' and isinstance(v,dict) and v.get('key')=='NET' and v.get('value')=='power_PWR_FLAG']
            assert len(stale_net_attrs)==len(remove),f'Unexpected PWR_FLAG net annotation count on {title}'
            d['records']=[(h,v) for h,v in d['records'] if not (h['type']=='COMPONENT' and h.get('id') in remove or h['type']=='ATTR' and isinstance(v,dict) and (h.get('id') in stale_net_attrs or v.get('parentId') in remove or any(v.get('parentId','').startswith(x+'e') for x in remove)))]
            report['pages'].append({'name':title,'global_labels_matched':sum(actual_globals.values()),'removed_erc_flags':sorted(actual_flags),'removed_false_wire_net_attributes':len(stale_net_attrs)})
        assert seen_pages==set(src),'Page mismatch'
        assert used_ports==netports,'Unused/ambiguous NetPort library cannot blindly rewrite'
        for u in used_ports:
            for h,v in symbols[u]['records']:
                if h['type']=='META':assert v['docType']==19;v['docType']=18
            report['patched_symbol_uuids'].append(u)
        for d in docs:
            if d['header'][1]['docType']=='INSTANCE':
                page=d['header'][1]['uuid'].split('_$')[-1];ids=removed.get(page,set())
                d['records']=[(h,v)for h,v in d['records'] if not(h['type']=='INSTANCE_ATTR' and h.get('id') in ids)]
        out='\n'.join(json.dumps(h,ensure_ascii=False,separators=(',',':'))+'||'+json.dumps(v,ensure_ascii=False,separators=(',',':'))+'|' for d in docs for h,v in [d['header']]+d['records'])+'\n'
        before_pcbs=[d for d in parse_docs(text) if d['header'][1]['docType']=='PCB'];after_pcbs=[d for d in parse_docs(out) if d['header'][1]['docType']=='PCB'];assert before_pcbs==after_pcbs,'PCB changed'
        with zipfile.ZipFile(a.output,'w',zipfile.ZIP_DEFLATED) as target:
            for n in z.namelist():target.writestr(n,out.encode() if n==entry else z.read(n))
    report['output']=str(a.output);report['output_sha256']=hashlib.sha256(a.output.read_bytes()).hexdigest();report['total_global_labels']=sum(x['global_labels_matched']for x in report['pages']);report['total_removed_erc_flags']=sum(len(x['removed_erc_flags'])for x in report['pages'])
    a.output.with_suffix('.schematic-fix-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
