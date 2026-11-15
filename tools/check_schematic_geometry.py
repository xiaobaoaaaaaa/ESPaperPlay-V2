#!/usr/bin/env python3
"""Read-only schematic wiring readability gate.

Actual API getState_Line flat arrays are independent segment quadruples.
Use --line-format polyline only for a creation plan containing vertex chains.
Electrical netlist comparison and visual review remain separate mandatory gates.
"""
import argparse, collections, itertools, json, math
from pathlib import Path
EPS=1e-6

def same(a,b): return math.dist(a,b)<=EPS

def cross(a,b): return a[0]*b[1]-a[1]*b[0]

def sub(a,b): return (a[0]-b[0],a[1]-b[1])

def on(p,a,b):
    return abs(cross(sub(p,a),sub(b,a)))<=EPS*max(1,math.dist(a,b)) and min(a[0],b[0])-EPS<=p[0]<=max(a[0],b[0])+EPS and min(a[1],b[1])-EPS<=p[1]<=max(a[1],b[1])+EPS

def intersection(a,b,c,d):
    r,s=sub(b,a),sub(d,c);den=cross(r,s)
    if abs(den)<=EPS:
        if abs(cross(sub(c,a),r))>EPS*max(1,math.dist(a,b)): return None
        points=[]
        for p in (a,b,c,d):
            if on(p,a,b) and on(p,c,d) and not any(same(p,q) for q in points):points.append(p)
        if not points:return None
        if len(points)==1:return ('point',points[0])
        p,q=max(itertools.combinations(points,2),key=lambda pq:math.dist(*pq))
        return ('overlap',(p,q)) if math.dist(p,q)>EPS else ('point',p)
    t=cross(sub(c,a),s)/den;u=cross(sub(c,a),r)/den
    if -EPS<=t<=1+EPS and -EPS<=u<=1+EPS:return ('point',(a[0]+t*r[0],a[1]+t*r[1]))
    return None

def segments(w,fmt):
    line=w['line']
    if not line:return []
    if isinstance(line[0],list):
        paths=line
    elif fmt=='segments':
        if len(line)%4:raise ValueError(f"API line length not multiple of four: {w.get('id')}")
        paths=[line[i:i+4]for i in range(0,len(line),4)]
    else:paths=[line]
    out=[]
    for path in paths:
        if len(path)%2:raise ValueError('Odd vertex coordinate count')
        pts=list(zip(path[::2],path[1::2]))
        out.extend((a,b)for a,b in zip(pts,pts[1:])if not same(a,b))
    return out

def body_bounds(c):
    if c.get('bodyBounds'):return c['bodyBounds'],False
    ps=c.get('pins',[])
    if not ps:return None,True
    inner=[]
    for p in ps:
        angle=math.radians(p.get('rotation',0));length=p.get('pinLength',10)
        inner.append((p['x']-math.cos(angle)*length,p['y']-math.sin(angle)*length))
    xs,ys=zip(*inner);xmin,xmax=min(xs),max(xs);ymin,ymax=min(ys),max(ys)
    if xmax-xmin<2:xmin-=4;xmax+=4
    if ymax-ymin<2:ymin-=4;ymax+=4
    return [xmin,xmax,ymin,ymax],True

def crosses_box(a,b,box):
    xmin,xmax,ymin,ymax=box
    xmin+=EPS;xmax-=EPS;ymin+=EPS;ymax-=EPS
    t0,t1=0.,1.;dx=b[0]-a[0];dy=b[1]-a[1]
    for p,q in [(-dx,a[0]-xmin),(dx,xmax-a[0]),(-dy,a[1]-ymin),(dy,ymax-a[1])]:
        if abs(p)<EPS:
            if q<0:return False
        else:
            r=q/p
            if p<0:t0=max(t0,r)
            else:t1=min(t1,r)
            if t0>t1:return False
    return t1-t0>EPS

def check(snapshot,mapping,fmt='segments'):
    if 'result'in snapshot:snapshot=snapshot['result']
    segs=[];findings=[];counts=collections.Counter()
    for i,w in enumerate(snapshot['wires']):
        for j,(a,b)in enumerate(segments(w,fmt)):
            segs.append({'wire':w.get('id',f'plan-wire-{i}'),'segment':j,'net':w['net'],'a':a,'b':b})
    for s,t in itertools.combinations(segs,2):
        hit=intersection(s['a'],s['b'],t['a'],t['b'])
        if hit is None:continue
        kind,point=hit;same_net=s['net']==t['net']
        if kind=='overlap':
            if s['wire']==t['wire']:kind='same_wire_retrace'
            elif same_net:kind='same_net_duplicate_overlap'
            else:kind='different_net_collinear_overlap'
        elif same_net:
            counts['same_net_junctions']+=1;continue
        else:
            se=same(point,s['a'])or same(point,s['b']);te=same(point,t['a'])or same(point,t['b'])
            kind='different_net_endpoint_contact'if se and te else 'different_net_T_contact'if se or te else 'different_net_visual_crossing'
        counts[kind]+=1
        findings.append({'kind':kind,'wires':[s['wire'],t['wire']],'nets':[s['net'],t['net']],'location':point})
    seen=set()
    for c in snapshot.get('components',[]):
        ref=c['ref'];mp=mapping.get(ref,{}).get('pins',{})
        for p in c.get('pins',[]):
            expected=mp.get(str(p['n']),{});wanted=''if expected.get('no_connect')else expected.get('net')
            for s in segs:
                if wanted is not None and s['net']!=wanted and on((p['x'],p['y']),s['a'],s['b']):
                    key=(ref,str(p['n']),s['wire'])
                    if key in seen:continue
                    seen.add(key);counts['wire_on_unrelated_pin']+=1
                    findings.append({'kind':'wire_on_unrelated_pin','reference':ref,'pin':str(p['n']),'expected_net':wanted,'wire_net':s['net'],'wire':s['wire'],'location':[p['x'],p['y']]})
        box,heuristic=body_bounds(c)
        if box:
            for s in segs:
                if crosses_box(s['a'],s['b'],box):
                    key=(ref,s['wire'],'body')
                    if key in seen:continue
                    seen.add(key);kind='estimated_body_intrusion_review'if heuristic else'exact_body_intrusion';counts[kind]+=1
                    findings.append({'kind':kind,'reference':ref,'wire':s['wire'],'net':s['net'],'bounds':box})
    hard=[f for f in findings if f['kind'].startswith('different_net') or f['kind'] in ['wire_on_unrelated_pin','exact_body_intrusion']]
    return {'status':'FAIL'if hard else'PASS_WITH_REVIEW'if findings else'PASS','scope':'Wire geometry readability only; no electrical connectivity or text-layout certification','line_format':fmt,'segments':len(segs),'components':len(snapshot.get('components',[])),'counts':dict(counts),'findings':findings,'limitations':['Native crossing semantics require exported netlist verification.','Body bounds inferred from pins are heuristic unless bodyBounds is provided.','Labels, titles and part text are not checked. Visual review remains required.']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('snapshot',type=Path);p.add_argument('mapping',type=Path);p.add_argument('--line-format',choices=['segments','polyline'],default='segments');p.add_argument('--output',type=Path);args=p.parse_args()
    mapping=json.loads(args.mapping.read_text());mapping=mapping.get('by_reference',mapping)
    result=check(json.loads(args.snapshot.read_text()),mapping,args.line_format);s=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(s)
    print(s,end='');return result['status']=='FAIL'
if __name__=='__main__':raise SystemExit(main())
