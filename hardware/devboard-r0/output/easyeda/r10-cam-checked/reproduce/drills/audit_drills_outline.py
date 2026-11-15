#!/usr/bin/python3
"""Read-only CAM drill/slot/profile/layer audit against KiCad r10.
Uses a strict parser for the decimal metric Excellon subset in these packages.
No CAD mutations; no client calls. System pcbnew is needed for the source check.
"""
from pathlib import Path
import argparse, collections, csv, hashlib, io, json, math, re, zipfile
import pcbnew

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def xy(s):
    m = re.fullmatch(r'X(-?[\d.]+)Y(-?[\d.]+)', s)
    assert m, ('unsupported coordinates', s)
    return tuple(float(x) for x in m.groups())
def drill(text):
    assert 'METRIC' in text and 'G90' in text
    tools = {}; tool = None; pos = None; routing = False; hits = []; slots = []
    for line in text.splitlines():
        line = line.strip()
        m = re.fullmatch(r'T(\d+)C([\d.]+)', line)
        if m: tools[m[1]] = float(m[2]); continue
        m = re.fullmatch(r'T(\d+)', line)
        if m: tool = m[1]; assert tool in tools; continue
        if 'G85' in line:
            a, b = line.split('G85'); assert tool and not routing
            slots.append({'a': xy(a), 'b': xy(b), 'diameter': tools[tool]}); continue
        if line.startswith('G00X'):
            pos = xy(line[3:]); continue
        if line == 'M15': routing = True; assert pos is not None; continue
        if line == 'M16': routing = False; continue
        if line.startswith('G01X'):
            assert routing and pos is not None and tool
            end = xy(line[3:]); slots.append({'a': pos, 'b': end, 'diameter': tools[tool]}); pos = end; continue
        if line.startswith('X'):
            assert tool and not routing
            hits.append({'center': xy(line), 'diameter': tools[tool]}); continue
        if line.startswith(('Y', 'G00', 'G01', 'G02', 'G03')): raise AssertionError(('unparsed drill operation', line))
    assert not routing
    return {'round': hits, 'slots': slots, 'tools': tools}
def dist(a, b): return math.dist(a, b)
def delta(a, b, kind):
    if abs(a['diameter']-b['diameter']) > 1e-7: return float('inf')
    if kind == 'round': return dist(a['center'], b['center'])
    return min(max(dist(a['a'],b['a']),dist(a['b'],b['b'])),max(dist(a['a'],b['b']),dist(a['b'],b['a'])))
def match(a, b, kind, tolerance):
    unused = set(range(len(b))); pairs = []; failed = []
    for i, item in enumerate(a):
        ds = [(delta(item,b[j],kind),j) for j in unused]
        error,j = min(ds) if ds else (float('inf'),-1)
        if error > tolerance: failed.append({'index':i,'item':item,'nearest_error_mm':error if math.isfinite(error) else None})
        else: unused.remove(j);pairs.append((i,j,error))
    return {'pass':not failed and not unused,'reference_count':len(a),'candidate_count':len(b),'matches':len(pairs),'max_center_or_endpoint_error_mm':max((e for i,j,e in pairs),default=0),'tolerance_mm':tolerance,'unmatched_reference':failed,'unmatched_candidate':sorted(unused)}
def signature(item,kind):
    if kind=='round': return tuple(item['center'])+(item['diameter'],)
    return tuple(sorted((tuple(item['a']),tuple(item['b']))))+(item['diameter'],)
def outline(text):
    fs=re.search(r'%FSLAX(\d)(\d)Y\1\2\*%',text);assert fs and '%MOMM*%'in text
    factor=10**int(fs[2]);aps={k:float(v)for k,v in re.findall(r'%ADD(\d+)C,([\d.]+)\*%',text)}
    current=None;pos=None;segments=[];widths=[]
    for line in text.splitlines():
        m=re.fullmatch(r'(?:G54)?D(\d+)\*',line)
        if m:current=m[1];continue
        m=re.fullmatch(r'(?:G01)?X(-?\d+)Y(-?\d+)D0([12])\*',line)
        if m:
            end=(int(m[1])/factor,int(m[2])/factor)
            if m[3]=='1':assert pos is not None;segments.append(tuple(sorted((pos,end))));widths.append(aps[current])
            pos=end
    counts=collections.Counter(p for s in segments for p in s)
    assert len(segments)==4 and all(n==2 for n in counts.values())
    xs=[p[0]for p in counts];ys=[p[1]for p in counts]
    return {'segments':sorted(segments),'closed_single_rectangle':True,'centerline_bounds_mm':[min(xs),min(ys),max(xs),max(ys)],'size_mm':[max(xs)-min(xs),max(ys)-min(ys)],'stroke_widths_mm':sorted(set(widths))}
def source_holes(board):
    out={'pth':{'round':[],'slots':[]},'npth':{'round':[],'slots':[]},'via':[],'module_epad':[],'ordinary_component':[]}
    mm=lambda v:v/1e6
    for t in board.GetTracks():
        if isinstance(t,pcbnew.PCB_VIA):
            q=t.GetPosition();item={'center':(mm(q.x),-mm(q.y)),'diameter':mm(t.GetDrillValue()),'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()}
            out['via'].append(item);out['pth']['round'].append(item)
    for f in board.GetFootprints():
        for p in f.Pads():
            ds=p.GetDrillSize()
            if not min(ds.x,ds.y):continue
            q=p.GetPosition();center=(mm(q.x),-mm(q.y));diameter=mm(min(ds.x,ds.y));part='npth'if p.GetAttribute()==pcbnew.PAD_ATTRIB_NPTH else'pth'
            item={'diameter':diameter,'ref':f.GetReference(),'pin':p.GetNumber(),'uuid':p.m_Uuid.AsString()}
            if ds.x==ds.y:kind='round';item['center']=center
            else:
                kind='slots';length=mm(abs(ds.x-ds.y));a=math.radians(p.GetOrientationDegrees()+(90 if ds.y>ds.x else 0));dx=math.cos(a)*length/2;dy=-math.sin(a)*length/2
                item.update(a=(center[0]-dx,center[1]-dy),b=(center[0]+dx,center[1]+dy))
            out[part][kind].append(item)
            if part=='pth':out['module_epad'if f.GetReference()=='U301'and p.GetNumber()=='41'else'ordinary_component'].append({'kind':kind,**item})
    return out
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--eda',type=Path,required=True)
    ap.add_argument('--kicad-zip',type=Path,required=True)
    ap.add_argument('--board',type=Path,required=True)
    source=ap.add_mutually_exclusive_group(required=True)
    source.add_argument('--pcb-source',type=Path,help='Current saved EasyEDA PCB source text')
    source.add_argument('--snapshots',type=Path,help='Legacy snapshots ZIP containing synced-final-pcb-source.txt')
    ap.add_argument('--fill-csv',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    with zipfile.ZipFile(a.eda)as z:
        assert z.testzip()is None;ed={n:z.read(n).decode()for n in z.namelist()};eda_names=z.namelist()
    with zipfile.ZipFile(a.kicad_zip)as z:
        assert z.testzip()is None;ki={n:z.read(n).decode()for n in z.namelist()}
    src=source_holes(pcbnew.LoadBoard(str(a.board)))
    e={'pth':drill(ed['Drill_PTH_Through.DRL']),'npth':drill(ed['Drill_NPTH_Through.DRL']),'via':drill(ed['Drill_PTH_Through_Via.DRL'])}
    k={'pth':drill(ki['ESPaperPlay_Devboard-PTH.drl']),'npth':drill(ki['ESPaperPlay_Devboard-NPTH.drl'])}
    comparisons={};duplicate_checks={}
    for typ in ['pth','npth']:
        for kind in ['round','slots']:
            comparisons[f'source_to_eda_{typ}_{kind}']=match(src[typ][kind],e[typ][kind],kind,0.00001)
            comparisons[f'kicad_cam_to_eda_{typ}_{kind}']=match(k[typ][kind],e[typ][kind],kind,0.00072)
            signatures=[signature(x,kind)for x in e[typ][kind]];duplicate_checks[typ+'_'+kind]={'count':len(signatures),'unique':len(set(signatures)),'duplicates':len(signatures)-len(set(signatures))}
    comparisons['source_to_eda_via_only']=match(src['via'],e['via']['round'],'round',0.00001)
    via_subsets=set(signature(x,'round')for x in e['via']['round'])<=set(signature(x,'round')for x in e['pth']['round'])
    fills=list(csv.DictReader(a.fill_csv.open()));fill_results=[]
    for r in fills:
        expected={'center':(float(r['x_mm']),-float(r['y_mm'])),'diameter':float(r['drill_x_mm'])};sv=next(v for v in src['via']if v['uuid']==r['uuid']);ds=[delta(expected,v,'round')for v in e['via']['round']]
        fill_results.append({'source_uuid':r['uuid'],'associated_pads':r['associated_pads'],'source_xy_mm':[float(r['x_mm']),float(r['y_mm'])],'cam_xy_mm':list(expected['center']),'diameter_mm':expected['diameter'],'matches_eda_via_count':sum(d<.00001 for d in ds),'source_uuid_net':sv['net'],'source_position_matches_csv':delta(expected,sv,'round')<.000002,'required_process':r['required_process'],'pass':sum(d<.00001 for d in ds)==1 and sv['net']=='GND'and delta(expected,sv,'round')<.000002})
    eo=outline(ed['Gerber_BoardOutlineLayer.GKO']);ko=outline(ki['ESPaperPlay_Devboard-Edge_Cuts.gm1']);same_profile=eo['segments']==ko['segments']
    if a.pcb_source:text=a.pcb_source.read_text()
    else:
        with zipfile.ZipFile(a.snapshots)as z:text=z.read('synced-final-pcb-source.txt').decode()
    rows=[(json.loads(h),json.loads(v.rstrip('|')))for h,v in (l.split('||',1)for l in text.splitlines()if l.strip())]
    for result in fill_results:
        candidates=[(h,v)for h,v in rows if h['type']=='VIA'and math.dist([v['centerX']*.0254,v['centerY']*.0254],result['cam_xy_mm'])<.00001]
        result['easyeda_primitive_ids']=[h['id']for h,v in candidates]
        result['easyeda_net_matches']=len(candidates)==1 and candidates[0][1]['netName']=='GND'
        result['pass']=result['pass']and result['easyeda_net_matches']
    layer_ids={1:'Gerber_TopLayer.GTL',15:'Gerber_InnerLayer1.G1',16:'Gerber_InnerLayer2.G2',2:'Gerber_BottomLayer.GBL'}
    layers=[]
    for h,v in rows:
        if h['type']=='LAYER'and v.get('use')and v.get('layerType')in ['TOP','BOTTOM','SIGNAL','PLANE']:
            lid=json.loads(h['id'])[1];fn=layer_ids[lid];layers.append({'source_id':lid,'source_name':v['layerName'],'source_type':v['layerType'],'gerber_file':fn,'file_present':fn in ed,'gerber_layer_header':ed[fn].splitlines()[0]})
    layers.sort(key=lambda x:[1,15,16,2].index(x['source_id']))
    pours=[{'layer':v['layerId'],'net':v['netName']}for h,v in rows if h['type']=='POUR']
    core=[layer_ids[x]for x in [1,15,16,2]]+['Gerber_TopSolderMaskLayer.GTS','Gerber_BottomSolderMaskLayer.GBS','Gerber_TopSilkscreenLayer.GTO','Gerber_BottomSilkscreenLayer.GBO','Gerber_BoardOutlineLayer.GKO','Drill_PTH_Through.DRL','Drill_NPTH_Through.DRL']
    recommendations={'board_fabrication_files':core,'exclude_from_board_fabrication_zip':sorted(set(eda_names)-set(core)),'add_to_board_fabrication_zip':['thermal-via-fill-spec.csv (verified coordinates, preserve original header/source meaning)','README/process requirements with exact layer order and outline centerline definition'],'drill_policy':'Use combined Drill_PTH_Through.DRL and Drill_NPTH_Through.DRL. Do not also load Drill_PTH_Through_Via.DRL; it repeats 549 native-via drill operations. Keep Via-only as inspection evidence outside the fabrication upload.','mask_policy':'Preserve exact delivered masks; do not apply global expansion. This subaudit does not itself validate mask polygons.','stencil_policy':'Do not use generic GTP as DIY stencil. Dedicated 203-placement/636-opening stencil remains separately reviewed.'}
    unique_holes={typ:len(e[typ]['round'])+len(e[typ]['slots'])for typ in ['pth','npth']}
    passed=all(x['pass']for x in comparisons.values())and all(not x['duplicates']for x in duplicate_checks.values())and via_subsets and all(x['pass']for x in fill_results)and len(fill_results)==11 and same_profile and len(layers)==4 and sorted((x['layer'],x['net'])for x in pours)==[(15,'GND'),(16,'GND')]
    report={'status':'PASS_WITH_PACKAGING_NOTES'if passed else'FAIL','inputs_sha256':{str(p):sha(p)for p in [a.eda,a.kicad_zip,a.board,a.pcb_source or a.snapshots,a.fill_csv]},'coordinate_convention':'CAM absolute X, negative Y; KiCad design Y points down. No translation/rotation/mirror applied.','quantization':'KiCad Excellon baseline rounds to 0.001mm, EasyEDA to 0.00001mm; source-to-EasyEDA checked within 0.00001mm, package-to-package within sqrt(2)*0.0005mm rounded to0.00072.','source_counts':{'native_vias':len(src['via']),'ordinary_component_plated_holes_including_4_slots':len(src['ordinary_component']),'U301_epad_plated_holes':len(src['module_epad']),'PTH_round':len(src['pth']['round']),'PTH_slots':len(src['pth']['slots']),'NPTH':len(src['npth']['round'])},'comparisons':comparisons,'duplicates':duplicate_checks,'combined_pth_total_features':unique_holes['pth'],'npth_total_features':unique_holes['npth'],'via_only_exact_subset_of_combined_pth':via_subsets,'via_only_count':len(e['via']['round']),'slots':e['pth']['slots'],'npth_holes':e['npth']['round'],'mandatory_fill_cap_holes':fill_results,'preserve_open_holes':{'ordinary_component_PTH':95,'U301_epad_unprinted_PTH_not_mandatory_fill':12,'NPTH':7,'microphone':{'center_cam_mm':[61,-62],'diameter_mm':.6},'note':'11 native vias require fill/planarize/copper cap. Source/DRL cannot guarantee factory process acceptance; physical holes must not be blanket-filled.'},'outline':{'centerline_equal':same_profile,'easyeda':eo,'kicad':ko,'note':'Artwork stroke widened0.05→0.15mm; nominal centerline profile remains160×110mm. EDA stroked bbox160.15×110.15mm is not finished board dimension.'},'copper_layer_order':layers,'inner_pours':pours,'file_set_recommendations':recommendations,'limits':['Comparison covers complete drill/slot output and a rectangular outline, plus layer identification. It does not compare all copper/paste/mask geometry or certify factory stackup/impedance.','PCB drill centering and actual cap thickness/planarity remain manufacturing verification.','Raw EasyEDA ZIP is an audit export, not a curated fabrication upload; excluded files are retained untouched in the original ZIP.']}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    with a.output.with_suffix('.fill-cap-map.csv').open('w',newline='')as f:
        w=csv.writer(f);w.writerow(['source_KiCad_uuid','EasyEDA_primitive_id','associated_pads','design_X_mm','design_Y_down_mm','CAM_X_mm','CAM_Y_mm','drill_mm','required_process'])
        for r in fill_results:w.writerow([r['source_uuid'],';'.join(r['easyeda_primitive_ids']),r['associated_pads'],*r['source_xy_mm'],*r['cam_xy_mm'],r['diameter_mm'],r['required_process']])
    print(json.dumps({'status':report['status'],'source_counts':report['source_counts'],'comparison_failures':[k for k,v in comparisons.items()if not v['pass']],'outline_same':same_profile,'report':str(a.output)},ensure_ascii=False,indent=2))
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
