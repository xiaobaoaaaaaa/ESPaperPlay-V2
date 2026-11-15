#!/usr/bin/env python3
"""Read-only KiCad / EasyEDA / manufacturing via audit; system pcbnew required."""
from pathlib import Path
import argparse, collections, hashlib, json, math, re, zipfile
import pcbnew

p=argparse.ArgumentParser()
p.add_argument('--source',type=Path,default=Path(__file__).parent/'final-pcb-source.txt')
p.add_argument('--gerber',type=Path,default=Path(__file__).parent/'gerber-clean.zip')
p.add_argument('--kicad',type=Path,default=Path('/home/xiaobao/Projects/ESPaperPlay-V2/hardware/devboard-r0/ESPaperPlay_Devboard.kicad_pcb'))
p.add_argument('--output',type=Path,default=Path(__file__).parent/'via-audit.json')
a=p.parse_args()
rows=[tuple(map(json.loads,l.rstrip('|').split('||',1)))for l in a.source.read_text().splitlines()]
v=[dict(id=h['id'],x=d['centerX']*.0254,y=-d['centerY']*.0254,hole=d['holeDiameter']*.0254,diameter=d['viaDiameter']*.0254,net=d['netName'])for h,d in rows if h['type']=='VIA']
b=pcbnew.LoadBoard(str(a.kicad))
k=[dict(id=t.m_Uuid.AsString(),x=pcbnew.ToMM(t.GetPosition().x),y=pcbnew.ToMM(t.GetPosition().y),hole=pcbnew.ToMM(t.GetDrillValue()),diameter=pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)),net=t.GetNetname())for t in b.GetTracks()if isinstance(t,pcbnew.PCB_VIA)]
dist=lambda u,w:math.hypot(u['x']-w['x'],u['y']-w['y'])
pairs=[(i,min(range(len(k)),key=lambda j:dist(t,k[j])))for i,t in enumerate(v)]
renames=collections.Counter((k[j]['net'],v[i]['net'])for i,j in pairs if k[j]['net']!=v[i]['net'])
report={'inputs':{str(f):hashlib.sha256(f.read_bytes()).hexdigest()for f in [a.source,a.gerber,a.kicad]},'units':'mm','via_count':{'kicad':len(k),'easyeda':len(v)},'unique_kicad_matches':len({j for i,j in pairs}),'max_position_difference_mm':max(dist(v[i],k[j])for i,j in pairs),'max_outer_diameter_difference_mm':max(abs(v[i]['diameter']-k[j]['diameter'])for i,j in pairs),'max_drill_diameter_difference_mm':max(abs(v[i]['hole']-k[j]['hole'])for i,j in pairs),'size_distribution':[{'outer_mm':d,'hole_mm':h,'count':n}for(d,h),n in sorted(collections.Counter((round(t['diameter'],5),round(t['hole'],5))for t in v).items())],'literal_network_renames':[{'kicad':x,'easyeda':y,'count':n}for(x,y),n in sorted(renames.items())]}
for arr,name in [(k,'kicad'),(v,'easyeda')]:
    dists=[(dist(t,u),t['id'],u['id'])for i,t in enumerate(arr)for u in arr[i+1:]]
    report[name+'_neighbor_check']={'min_distance_mm':min(dists)[0],'duplicate_centers_within_0_00001mm':sum(d<.00001 for d,x,y in dists),'pairs_below_0_4mm':sum(d<.4 for d,x,y in dists),'pairs_below_0_6mm':sum(d<.6 for d,x,y in dists)}
report['possible_other_geometry']={'standalone_pad_count':sum(h['type']=='PAD'for h,d in rows),'poly_layers':dict(collections.Counter(str(d['layerId'])for h,d in rows if h['type']=='POLY')),'primitive_records_are_display_pick_settings':all(set(d)<= {'display','pick'}for h,d in rows if h['type']=='PRIMITIVE'),'fill_count':sum(h['type']=='FILL'for h,d in rows)}
drill={};report['drill_files']={};report['copper_layer_via_flashes']={}
with zipfile.ZipFile(a.gerber)as z:
    assert z.testzip()is None
    for fn in [n for n in z.namelist()if n.endswith('.DRL')]:
        txt=z.read(fn).decode();tools={};tool=None;pts=[];slots=[]
        for line in txt.splitlines():
            m=re.match(r'T(\d+)C([\d.]+)',line)
            if m:tools[m[1]]=float(m[2]);continue
            m=re.fullmatch(r'T(\d+)',line)
            if m:tool=m[1];continue
            m=re.fullmatch(r'X(-?[\d.]+)Y(-?[\d.]+)',line)
            if m:pts.append((float(m[1]),-float(m[2]),tools[tool]))
            if 'G85' in line:slots.append(line)
        drill[fn]=pts
        report['drill_files'][fn]={'round_hits':len(pts),'unique_round_hits':len(set(pts)),'slot_commands':len(slots),'diameters':dict(collections.Counter(str(t[2])for t in pts))}
    pts=drill['Drill_PTH_Through_Via.DRL']
    report['via_drill_comparison']={'max_position_difference_mm':max(min(math.hypot(x-t['x'],y-t['y'])for t in k)for x,y,d in pts),'unmatched_position_or_diameter_count':sum(not any(math.hypot(x-t['x'],y-t['y'])<.00001 and abs(d-t['hole'])<.000001 for t in k)for x,y,d in pts),'via_only_drill_is_subset_of_combined_pth':set(pts)<=set(drill['Drill_PTH_Through.DRL'])}
    for fn in ['Gerber_TopLayer.GTL','Gerber_BottomLayer.GBL','Gerber_InnerLayer1.G1','Gerber_InnerLayer2.G2']:
        s=z.read(fn).decode();chunks=re.findall(r'G04 Via Start\*(.*?)G04 Via End\*',s,re.S);assert len(chunks)==1
        aps={code:float(d)for code,d in re.findall(r'%ADD(\d+)C,([\d.]+)\*%',s)};sel=None;flashes=[]
        for line in chunks[0].splitlines():
            m=re.search(r'G54D(\d+)\*',line)
            if m:sel=m[1]
            m=re.search(r'X(-?\d+)Y(-?\d+)D03\*',line)
            if m:flashes.append((int(m[1])/1e5,-int(m[2])/1e5,aps.get(sel)))
        report['copper_layer_via_flashes'][fn]={'count':len(flashes),'unique':len(set(flashes)),'outer_diameters':dict(collections.Counter(str(d)for x,y,d in flashes)),'max_position_difference_mm':max(min(math.hypot(x-t['x'],y-t['y'])for t in v)for x,y,d in flashes),'unmatched_position_or_diameter_count':sum(not any(math.hypot(x-t['x'],y-t['y'])<.00001 and abs(d-t['diameter'])<.000002 for t in v)for x,y,d in flashes)}
report['geometric_and_drill_audit_passed']=(len(v)==len(k)==549 and report['unique_kicad_matches']==549 and report['max_position_difference_mm']<.00001 and report['max_outer_diameter_difference_mm']<.000002 and report['max_drill_diameter_difference_mm']<.000002 and report['easyeda_neighbor_check']['duplicate_centers_within_0_00001mm']==0 and len(pts)==len(set(pts))==549 and report['via_drill_comparison']['unmatched_position_or_diameter_count']==0 and all(q['count']==q['unique']==549 and q['unmatched_position_or_diameter_count']==0 for q in report['copper_layer_via_flashes'].values()))
report['notes']=['User confirmed that the apparently extra holes were intended GND vias.','This audit checks via geometry, copper flashes and physical drill outputs; renamed network strings require the separate project netlist equivalence check.','The combined PTH drill file already contains the via-only file; do not add both counts together.','Board-level connectivity, clearances, footprints and stencil validation are outside this via-specific audit.']
a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'report':str(a.output),'passed':report['geometric_and_drill_audit_passed'],'vias':len(v),'literal_renamed_vias':sum(renames.values())}))
