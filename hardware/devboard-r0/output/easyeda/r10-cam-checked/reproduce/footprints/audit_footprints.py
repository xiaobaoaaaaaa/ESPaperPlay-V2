#!/usr/bin/python3
"""Read-only full footprint pad correspondence and manufacturing geometry audit."""
import json,math,collections,hashlib,argparse
from pathlib import Path
import pcbnew

def rows(text):
 d={}
 for line in text.splitlines():
  if not line.strip():continue
  h,v=line.split('||',1);h=json.loads(h);v=json.loads(v.rstrip('|'))if v.rstrip('|')else None;k=(h['type'],h.get('id'))
  if k not in d or h.get('ticket',0)>=d[k][0].get('ticket',0):d[k]=h,v
 return[(h,v)for h,v in d.values()if v is not None]
def xy(v):return[v.x/1e6,v.y/1e6]
def angle_delta(a,b):return abs((a-b+90)%180-90)
def global_xy(c,p):
 t=math.radians(c['angle']);x=p['centerX'];y=p['centerY'];return[(c['x']+x*math.cos(t)-y*math.sin(t))*.0254,-(c['y']+x*math.sin(t)+y*math.cos(t))*.0254]

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--board',type=Path,required=True);ap.add_argument('--source',type=Path,default=Path(__file__).parent/'synced-final-pcb-source.txt');ap.add_argument('--footprints',type=Path,default=Path(__file__).parent/'final-footprint-sources.json');ap.add_argument('--output',type=Path,default=Path(__file__).parent/'footprint-audit.json');ap.add_argument('--npth-repairs',type=Path,help='Explicit prepared1um copper exception requests; preserves and both mask apertures are checked, not skipped.');args=ap.parse_args()
 exceptions={}
 if args.npth_repairs:
  for req in json.loads(args.npth_repairs.read_text())['requests']:
   for ref in req['refs']:
    key=(ref,req['pad_id']);assert key not in exceptions;exceptions[key]=req
 seen_exceptions=set()
 data=rows(args.source.read_text());attrs=collections.defaultdict(dict)
 for h,v in data:
  if h['type']=='ATTR':attrs[v['parentId']][v['key']]=v['value']
 comps={attrs[h['id']]['Designator']:(h,v,attrs[h['id']])for h,v in data if h['type']=='COMPONENT'}
 fps={x['uuid']:rows(x['source'])for x in json.loads(args.footprints.read_text())['result']};board=pcbnew.LoadBoard(str(args.board));kfps={f.GetReference():f for f in board.GetFootprints()};assert comps.keys()==kfps.keys()
 report={'inputs':{str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in[args.board,args.source,args.footprints]},'component_count':len(comps),'tolerances':{'source_coordinate_size_mm':.000005,'angle_deg':.00001},'pads':[],'custom_pads':[],'problems':[],'statistics':{}}
 tol=.000005
 for ref,(ch,c,at)in comps.items():
  f=kfps[ref];ep=[(h,v)for h,v in fps[at['Footprint']]if h['type']=='PAD'];used=set();kp=[p for p in f.Pads()if p.IsOnLayer(pcbnew.F_Cu)or p.IsOnLayer(pcbnew.B_Cu)]
  # U803 original annular copper pad4 is represented by four simple sectors.
  for pad in kp:
   num=pad.GetNumber();pos=xy(pad.GetPosition());size=xy(pad.GetSize());angle=pad.GetOrientationDegrees();shape=pad.GetShape();candidates=[(i,h,v)for i,(h,v)in enumerate(ep)if i not in used and v.get('num')==num]
   if shape==pcbnew.PAD_SHAPE_CUSTOM:
    assert ref=='U803'and num=='4'
    assert len(candidates)==4
    for i,h,v in candidates:used.add(i)
    report['custom_pads'].append({'ref':ref,'number':num,'source_shape':'custom annulus','converted_ids':[h['id']for i,h,v in candidates],'coordinate_mm':pos,'validation':'See independent exact arc Gerber ring audit; no generic shape substitution assumed.'});continue
   if not candidates:report['problems'].append({'ref':ref,'pin':num,'problem':'unmatched source pad','position':pos});continue
   i,h,e=min(candidates,key=lambda z:math.dist(global_xy(c,z[2]),pos));used.add(i)
   epos=global_xy(c,e);esz=e['defaultPad'];ea=c['angle']+e['padAngle'];width=esz.get('width',0)*.0254;height=esz.get('height',0)*.0254;drill=xy(pad.GetDrillSize());exception=exceptions.get((ref,h['id']));eh=e.get('hole')or{};edrill=[eh.get('width',0)*.0254,eh.get('height',0)*.0254];ekind=esz['padType'];errors=[]
   off=math.dist(pos,epos)
   if off>tol:errors.append('pad center')
   desired={pcbnew.PAD_SHAPE_RECT:'RECT',pcbnew.PAD_SHAPE_ROUNDRECT:'RECT',pcbnew.PAD_SHAPE_CIRCLE:'ELLIPSE',pcbnew.PAD_SHAPE_OVAL:'OVAL'}.get(shape)
   if ekind!=desired:errors.append('shape type')
   direct=max(abs(size[0]-width),abs(size[1]-height));swapped=max(abs(size[0]-height),abs(size[1]-width));ad=angle_delta(angle,ea)
   # A swapped width/height plus quarter-turn is the same geometry.
   if exception:
    seen_exceptions.add((ref,h['id']))
    if pad.GetAttribute()!=pcbnew.PAD_ATTRIB_NPTH or num!='':errors.append('illegal NPTH exception')
    expected=exception['set']['defaultPad'];expected_mm=[expected['width']*.0254,expected['height']*.0254]
    quantized_mm=[round(expected['width'],4)*.0254,round(expected['height'],4)*.0254]
    if min(max(abs(width-expected_mm[0]),abs(height-expected_mm[1])),max(abs(width-quantized_mm[0]),abs(height-quantized_mm[1])))>1e-10 or max(abs(z-.001)for z in expected_mm)>1e-10:errors.append('NPTH requested 1um copper size or exact4decimalmilserialization')
    for key,value in exception['preserve'].items():
     if e.get(key)!=value:errors.append('NPTH preserved field '+key)
   elif direct<=tol and ad<.00001:pass
   elif swapped<=tol and abs(ad-90)<.00001:pass
   elif abs(size[0]-size[1])<tol and direct<=tol and (desired=='ELLIPSE'or ad<.00001 or abs(ad-90)<.00001):pass
   else:errors.append('size/orientation')
   r=pad.GetRoundRectCornerRadius()/1e6 if shape==pcbnew.PAD_SHAPE_ROUNDRECT else 0;er=min(width,height)*esz.get('radius',0)/200 if ekind=='RECT'else 0
   if abs(r-er)>tol:errors.append('corner radius')
   hole_direct=max(abs(drill[j]-edrill[j])for j in[0,1]);hole_swapped=max(abs(drill[j]-edrill[1-j])for j in[0,1]);hole_angle=ea+(e.get('relativeAngle')or 0);hole_ad=angle_delta(angle,hole_angle)
   if max(drill+edrill)>tol and not ((hole_direct<=tol and (abs(drill[0]-drill[1])<tol or hole_ad<.00001)) or (hole_swapped<=tol and abs(hole_ad-90)<.00001)):errors.append('hole size/orientation')
   plated=pad.GetAttribute()!=pcbnew.PAD_ATTRIB_NPTH
   if bool(e['plated'])!=plated:errors.append('plating')
   klayers=[n for n,li in [('F.Cu',pcbnew.F_Cu),('In1.Cu',pcbnew.In1_Cu),('In2.Cu',pcbnew.In2_Cu),('B.Cu',pcbnew.B_Cu)]if pad.IsOnLayer(li)]
   elayers={1:['F.Cu'],2:['B.Cu'],12:['F.Cu','In1.Cu','In2.Cu','B.Cu']}.get(e['layerId'])
   if klayers!=elayers:errors.append('copper layer span')
   mask=[]
   for layer,key,name in [(pcbnew.F_Mask,'topSolderExpansion','F.Mask'),(pcbnew.B_Mask,'bottomSolderExpansion','B.Mask')]:
    present=pad.IsOnLayer(layer);margin=pad.GetSolderMaskExpansion(layer)/1e6;emargin=(e.get(key)or 0)*.0254
    # Auto mask only on corresponding exposed copper layer; NPTH included.
    epresent=e['layerId']in ([1,12]if layer==pcbnew.F_Mask else[2,12]) and min(width,height)+2*emargin>0
    if present!=epresent:errors.append('mask layer membership '+name)
    if present and exception:
     if max(abs(size[0]+2*margin-width-2*emargin),abs(size[1]+2*margin-height-2*emargin))>tol:errors.append('NPTH compensated mask aperture '+name)
    elif present and abs(margin-emargin)>tol:errors.append('mask margin '+name)
    mask.append({'layer':name,'source_present':present,'converted_present':epresent,'source_margin_mm':margin,'converted_margin_mm':emargin,'source_opening_size_mm':[size[0]+2*margin,size[1]+2*margin],'converted_opening_size_mm':[width+2*emargin,height+2*emargin]})
   entry={'ref':ref,'number':num,'source_pad_uuid':pad.m_Uuid.AsString(),'converted_id':h['id'],'source_center_mm':pos,'converted_center_mm':epos,'center_delta_mm':off,'source_size_mm':size,'converted_size_mm':[width,height],'source_rotation_deg':angle,'converted_rotation_deg':ea,'source_corner_radius_mm':r,'converted_corner_radius_mm':er,'source_drill_mm':drill,'converted_drill_mm':edrill,'source_shape':int(shape),'converted_shape':ekind,'layers':klayers,'mask':mask,'problems':errors}
   if exception:entry['intentional_npth_copper_exception']={'target_diameter_mm':.001,'actual_source_diameter_mm':width,'source_serialization_error_mm':width-.001,'accepted_serialization':'Exact request or request rounded to4decimal mil; no other size exception.','requested_fields_verified':list(exception['set']),'preserved_fields_verified':list(exception['preserve']),'nominal_drill_radial_margin_mm':(min(drill)-max(width,height))/2}
   report['pads'].append(entry)
   if errors:report['problems'].append(entry)
  remaining=[h['id']for i,(h,v)in enumerate(ep)if i not in used]
  if remaining:report['problems'].append({'ref':ref,'problem':'extra unmatched converted pad','ids':remaining})
 if seen_exceptions!=exceptions.keys():report['problems'].append({'problem':'unmatched explicit NPTH exceptions','keys':sorted(exceptions.keys()-seen_exceptions)})
 report['npth_exception_count']=len(seen_exceptions)
 report['statistics']={'matched_standard_pad_count':len(report['pads']),'custom_source_pad_count':len(report['custom_pads']),'converted_custom_sectors':sum(len(x['converted_ids'])for x in report['custom_pads']),'max_center_delta_mm':max(x['center_delta_mm']for x in report['pads']),'problem_type_counts':dict(collections.Counter(e for x in report['problems']for e in x.get('problems',[x.get('problem')]))),'problem_count':len(report['problems'])}
 report['status']='PASS'if not report['problems']else'FAIL';args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');print(json.dumps({k:v for k,v in report.items()if k not in['pads','inputs','problems']},indent=2,ensure_ascii=False));print('problem_count='+str(len(report['problems'])))
if __name__=='__main__':main()
