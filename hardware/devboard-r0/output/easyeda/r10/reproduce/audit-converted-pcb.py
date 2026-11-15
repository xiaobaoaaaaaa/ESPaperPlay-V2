#!/usr/bin/env python3
"""Read-only numeric comparison of converted EDA PCB source with KiCad r10."""
from pathlib import Path
import collections, json, math, sys
import pcbnew

BASE=Path(__file__).resolve().parent
TOL=0.000005  # mm; EDA source quantizes coordinates to 0.0001 mil.
input_name=sys.argv[1] if len(sys.argv)>1 else 'compat-pcb-source.txt'
output_name=sys.argv[2] if len(sys.argv)>2 else 'compat-converted-audit.json'
rows=[tuple(map(json.loads,l.rstrip('\n|').split('||',1))) for l in (BASE/input_name).read_text().splitlines()]
board=pcbnew.LoadBoard(str(BASE/'source/ESPaperPlay_Devboard.kicad_pcb'))
records=lambda kind: [(h,v) for h,v in rows if h['type']==kind]
refs={v['parentId']:v['value'] for h,v in records('ATTR') if v['key']=='Designator'}
comp={refs[h['id']]:v for h,v in records('COMPONENT')}
layers={h['id']:v for h,v in records('LAYER')}
layer_map={1:'F.Cu',2:'B.Cu',15:'In1.Cu',16:'In2.Cu'}
mm=lambda p: (pcbnew.ToMM(p.x),pcbnew.ToMM(p.y))
point=lambda x,y:(x*0.0254,-y*0.0254)
src=[]
for t in board.GetTracks():
    if t.GetClass()=='PCB_TRACK':
        src.append({'net':t.GetNetname(),'layer':board.GetLayerName(t.GetLayer()),'a':mm(t.GetStart()),'b':mm(t.GetEnd()),'width':pcbnew.ToMM(t.GetWidth())})
dst=[{'net':v['netName'],'layer':layer_map[v['layerId']],'a':point(v['startX'],v['startY']),'b':point(v['endX'],v['endY']),'width':v['width']*.0254} for h,v in records('LINE')]

def unmatched_coverage(lines, targets):
    groups=collections.defaultdict(list)
    for t in targets: groups[(t['net'],t['layer'])].append(t)
    unmatched=[]
    for line in lines:
        ax,ay=line['a']; bx,by=line['b']; dx=bx-ax;dy=by-ay;length=math.hypot(dx,dy);ux=dx/length;uy=dy/length
        intervals=[]
        for t in groups[(line['net'],line['layer'])]:
            if abs(t['width']-line['width'])>TOL: continue
            pts=[(p[0]-ax,p[1]-ay) for p in (t['a'],t['b'])]
            if max(abs(x*uy-y*ux) for x,y in pts)>TOL: continue
            lo,hi=sorted(x*ux+y*uy for x,y in pts)
            if hi>=-TOL and lo<=length+TOL: intervals.append((max(0,lo),min(length,hi)))
        covered=0
        gaps=[]
        for lo,hi in sorted(intervals):
            if lo>covered+TOL: gaps.append([covered,lo])
            covered=max(covered,hi)
        if covered<length-TOL: gaps.append([covered,length])
        if gaps: unmatched.append({**line,'covered_to_mm':covered,'length_mm':length,'uncovered_intervals_mm':gaps,'uncovered_length_mm':sum(hi-lo for lo,hi in gaps)})
    return unmatched

missing_tracks=unmatched_coverage(src,dst)
extra_tracks=unmatched_coverage(dst,src)
source_nets={n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
dest_nets={json.loads(h['id'])[1] for h,v in records('NET') if json.loads(h['id'])[1]}
source_pads=collections.Counter((f.GetReference(),p.GetNumber(),p.GetNetname()) for f in board.GetFootprints() for p in f.Pads() if p.GetNetname())
dest_pads=collections.Counter((refs[json.loads(h['id'])[1]],json.loads(h['id'])[2],v['padNet']) for h,v in records('PAD_NET') if v['padNet'])
source_fps={f.GetReference():f for f in board.GetFootprints()}
pos_errors=[math.dist(mm(source_fps[r].GetPosition()),point(v['x'],v['y'])) for r,v in comp.items() if r in source_fps]
angle_errors=[min((source_fps[r].GetOrientationDegrees()-v['angle'])%360,(v['angle']-source_fps[r].GetOrientationDegrees())%360) for r,v in comp.items() if r in source_fps]
source_vias=[t for t in board.GetTracks() if t.GetClass()=='PCB_VIA']
dest_vias=[v for h,v in records('VIA')]
via_unmatched=[]
available=set(range(len(dest_vias)))
max_via_pos_error=0
for t in source_vias:
    candidates=[i for i in available if dest_vias[i]['netName']==t.GetNetname() and math.dist(mm(t.GetPosition()),point(dest_vias[i]['centerX'],dest_vias[i]['centerY']))<TOL and abs(dest_vias[i]['holeDiameter']*.0254-pcbnew.ToMM(t.GetDrillValue()))<TOL and abs(dest_vias[i]['viaDiameter']*.0254-pcbnew.ToMM(t.GetWidth(t.TopLayer())))<TOL]
    if not candidates: via_unmatched.append({'net':t.GetNetname(),'position':mm(t.GetPosition())})
    else:
        i=candidates[0];available.remove(i)
        max_via_pos_error=max(max_via_pos_error,math.dist(mm(t.GetPosition()),point(dest_vias[i]['centerX'],dest_vias[i]['centerY'])))

report={
 'coordinate_tolerance_mm':TOL,
 'components':{'source_count':len(source_fps),'converted_count':len(comp),'missing_refs':sorted(set(source_fps)-set(comp)),'extra_refs':sorted(set(comp)-set(source_fps)),'max_position_error_mm':max(pos_errors),'max_rotation_error_degrees':max(angle_errors),'source_layers':dict(collections.Counter(board.GetLayerName(f.GetLayer()) for f in source_fps.values())),'converted_layers':dict(collections.Counter(layer_map[c['layerId']] for c in comp.values()))},
 'nets':{'source_nonempty':len(source_nets),'converted_nonempty':len(dest_nets),'missing':sorted(source_nets-dest_nets),'extra':sorted(dest_nets-source_nets),'case_normalized_sets_equal':{n.upper() for n in source_nets}=={n.upper() for n in dest_nets},'case_only_renames':len(source_nets-dest_nets)},
 'pad_net_assignments':{'source_netted_physical_pads':sum(source_pads.values()),'converted_netted_entries':sum(dest_pads.values()),'missing':list((source_pads-dest_pads).items()),'extra':list((dest_pads-source_pads).items()),'source_total_physical_pads':sum(len(f.Pads()) for f in source_fps.values()),'converted_pad_net_records':len(records('PAD_NET')),'note':'PAD_NET records do not enumerate all unconnected physical pads; footprint geometry requires separate library/API validation.'},
 'tracks':{'source_segments':len(src),'converted_segments':len(dst),'source_total_centerline_length_mm':sum(math.dist(t['a'],t['b']) for t in src),'converted_total_centerline_length_mm':sum(math.dist(t['a'],t['b']) for t in dst),'source_not_covered':missing_tracks,'converted_not_covered':extra_tracks,'coverage_requires_same_net_layer_width':True,'uncovered_segment_count':len(missing_tracks),'uncovered_max_length_mm':max((x['length_mm'] for x in missing_tracks),default=0),'uncovered_total_length_mm':sum(x['length_mm'] for x in missing_tracks)},
 'vias':{'source_count':len(source_vias),'converted_count':len(dest_vias),'unmatched_source':via_unmatched,'unmatched_converted':sorted(available),'max_position_error_mm':max_via_pos_error,'source_spans':dict(collections.Counter(f'{board.GetLayerName(t.TopLayer())}/{board.GetLayerName(t.BottomLayer())}' for t in source_vias)),'converted_types':dict(collections.Counter(v['viaType'] for v in dest_vias))},
 'copper_layers':{'source_count':board.GetCopperLayerCount(),'converted_enabled':[{k:v[k] for k in ('layerId','layerType','layerName')} for h,v in records('LAYER') if v['use'] and v['layerType'] in ('TOP','BOTTOM','SIGNAL','PLANE')]},
 'pours':{'source':[(z.GetNetname(),board.GetLayerName(z.GetLayer())) for z in board.Zones()],'converted':[(v['netName'],layer_map[v['layerId']]) for h,v in records('POUR')],'fill_equivalence_verified':False},
 'limitations':['This compares parsed source and centerline coverage, not DRC or fabricated electrical behavior.','Footprint internal physical pad geometry and filled copper differences need separate validation.']
}
(BASE/output_name).write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'report':output_name,'components':report['components'],'nets_count':len(dest_nets),'pad_net_missing':len(report['pad_net_assignments']['missing']),'pad_net_extra':len(report['pad_net_assignments']['extra']),'tracks':{k:v for k,v in report['tracks'].items() if k not in ('source_not_covered','converted_not_covered')},'converted_not_covered_count':len(extra_tracks),'vias':report['vias']},indent=2,ensure_ascii=False))
