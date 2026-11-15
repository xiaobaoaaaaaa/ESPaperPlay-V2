#!/usr/bin/env python3
"""Self-contained post-drill inner CAM comparison against the original KiCad board.

Requires system pcbnew, gerbonara1.6.x and shapely2.x. All input/output locations
are explicit CLI arguments. The optional SHA-256 keyed cache is an acceleration;
no pre-existing WKB files or project checkout path are required.
"""
from pathlib import Path
import json, hashlib, warnings
from gerbonara import GerberFile
from gerbonara.utils import MM
from shapely.geometry import Polygon, GeometryCollection
from shapely.ops import unary_union
from shapely import from_wkb

EPS=0.00005

def object_geometry(obj):
    result=GeometryCollection()
    for prim in obj.to_primitives(MM):
        points=prim.to_arc_poly().approximate_arcs(EPS).outline
        if len(points)<3: continue
        geom=Polygon(points).buffer(0)
        # Primitive polarity is absolute; normalize it relative to this object
        # before applying the object's layer polarity once below.
        result=result.union(geom) if prim.polarity_dark==obj.polarity_dark else result.difference(geom)
    return result

def read_geometry(path, cache=None, with_objects=False):
    path=Path(path);digest=hashlib.sha256(path.read_bytes()).hexdigest()
    cache=Path(cache) if cache else None
    target=cache/(digest+'.wkb') if cache else None
    if target and target.exists() and not with_objects:
        return from_wkb(target.read_bytes()),json.loads(target.with_suffix('.json').read_text())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always');file=GerberFile.open(path)
    result=GeometryCollection();pending=[];polarity=None;records=[]
    for idx,obj in enumerate(file.objects):
        if polarity is not None and obj.polarity_dark!=polarity:
            chunk=unary_union(pending)
            result=result.union(chunk) if polarity else result.difference(chunk)
            pending=[]
        polarity=obj.polarity_dark
        geom=object_geometry(obj);pending.append(geom)
        if with_objects:records.append((obj,geom))
    if pending:
        chunk=unary_union(pending)
        result=result.union(chunk) if polarity else result.difference(chunk)
    meta={'sha256':digest,'object_count':len(file.objects),'dark_objects':sum(o.polarity_dark for o in file.objects),
          'clear_objects':sum(not o.polarity_dark for o in file.objects),'area_mm2':result.area,'bounds_mm':list(result.bounds),
          'valid':result.is_valid,'curve_tolerance_mm':EPS,'warnings':[str(w.message)for w in caught]}
    if target:
        cache.mkdir(parents=True,exist_ok=True);target.write_bytes(result.wkb)
        target.with_suffix('.json').write_text(json.dumps(meta,indent=2))
    return (result,meta,records) if with_objects else (result,meta)

def components(g):
    if g.is_empty:return []
    if g.geom_type=='Polygon':return [g]
    return [p for p in g.geoms if p.geom_type=='Polygon']

def comparison(a,b):
    removed=a.difference(b);added=b.difference(a)
    significant_removed=a.difference(b.buffer(.005));significant_added=b.difference(a.buffer(.005))
    def top(g):
        return [{'area_mm2':p.area,'bounds_mm':list(p.bounds),'centroid_mm':[p.centroid.x,p.centroid.y]}for p in sorted(components(g),key=lambda p:-p.area)[:30]]
    return {'source_area_mm2':a.area,'migrated_area_mm2':b.area,'removed_area_mm2':removed.area,'added_area_mm2':added.area,
            'removed_beyond_5um_mm2':significant_removed.area,'added_beyond_5um_mm2':significant_added.area,
            'largest_removed_beyond_5um':top(significant_removed),'largest_added_beyond_5um':top(significant_added)}


import argparse, math, importlib.metadata
import pcbnew
from shapely.geometry import Point, LineString

def holes_from_board(board):
    holes=[];counts={'vias':0,'plated_pad_round':0,'plated_pad_slots':0,'non_plated_round':0,'non_plated_slots':0}
    for item in board.GetTracks():
        if isinstance(item,pcbnew.PCB_VIA):
            q=item.GetPosition();holes.append(Point((q.x/1e6,-q.y/1e6)).buffer(item.GetDrillValue()/2e6,quad_segs=256));counts['vias']+=1
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            drill=pad.GetDrillSize()
            if not drill.x:continue
            q=pad.GetPosition();center=(q.x/1e6,-q.y/1e6);radius=min(drill.x,drill.y)/2e6
            plated=pad.GetAttribute()==pcbnew.PAD_ATTRIB_PTH
            if drill.x==drill.y:
                hole=Point(center).buffer(radius,quad_segs=256);kind='round'
            else:
                length=abs(drill.x-drill.y)/1e6
                angle=math.radians(pad.GetOrientationDegrees()+(90 if drill.y>drill.x else 0))
                dx=math.cos(angle)*length/2;dy=-math.sin(angle)*length/2
                hole=LineString([(center[0]-dx,center[1]-dy),(center[0]+dx,center[1]+dy)]).buffer(radius,quad_segs=256);kind='slots'
            holes.append(hole);counts[('plated_pad_'if plated else'non_plated_')+kind]+=1
    return unary_union(holes),counts

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--board',type=Path,required=True,help='Original KiCad .kicad_pcb containing authoritative drill geometry')
    ap.add_argument('--source-dir',type=Path,required=True,help='Extracted original KiCad CAM with *-In1_Cu.g1 and *-In2_Cu.g2')
    ap.add_argument('--previous-eda-dir',type=Path,required=True,help='Extracted pre-repair EasyEDA CAM')
    ap.add_argument('--eda-dir',type=Path,required=True,help='Extracted current EasyEDA CAM')
    ap.add_argument('--cache',type=Path,help='Optional regenerable SHA-256 geometry cache')
    ap.add_argument('--output',type=Path,required=True,help='JSON report; companion WKB files are written alongside')
    args=ap.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    board=pcbnew.LoadBoard(str(args.board));holes,hole_counts=holes_from_board(board)
    report={'inputs':{k:str(v)for k,v in vars(args).items()if v is not None},'board_sha256':hashlib.sha256(args.board.read_bytes()).hexdigest(),'versions':{'pcbnew':pcbnew.GetBuildVersion(),'gerbonara':importlib.metadata.version('gerbonara'),'shapely':importlib.metadata.version('shapely')},'hole_counts':hole_counts,'hole_union_area_mm2':holes.area,'layers':[],'limits':'Actual native-board drill and slot solids are subtracted before copper comparison. Drill circles use256 segments per quadrant; Gerber curves use5e-5mm approximation. The5um lens is diagnostic, not a factory tolerance. Polygonization of a hole-sized NPTH flash can leave minute numerical slivers; inspect them before classifying retained copper. DRC, source semantics and electrical connectivity require separate checks.'}
    memo={}
    def compare(a,b):
        key=hashlib.sha256(a.wkb+b.wkb).hexdigest()
        if key not in memo:
            value=comparison(a,b)
            for tolerance in (.01,.015):
                value[f'removed_beyond_{int(tolerance*1000)}um_mm2']=a.difference(b.buffer(tolerance)).area
                value[f'added_beyond_{int(tolerance*1000)}um_mm2']=b.difference(a.buffer(tolerance)).area
            memo[key]=value
        return memo[key]
    for num in (1,2):
        matches=list(args.source_dir.glob(f'*-In{num}_Cu.g{num}'));assert len(matches)==1,matches
        a,am=read_geometry(matches[0],args.cache)
        old,om=read_geometry(args.previous_eda_dir/f'Gerber_InnerLayer{num}.G{num}',args.cache)
        current,cm=read_geometry(args.eda_dir/f'Gerber_InnerLayer{num}.G{num}',args.cache)
        aa=a.difference(holes);oo=old.difference(holes);cc=current.difference(holes)
        result={'layer':num,'source_meta':am,'previous_meta':om,'current_meta':cm,'source_component_count':len(components(aa)),'current_component_count':len(components(cc)),'baseline_comparison':compare(aa,oo),'repaired_comparison':compare(aa,cc),'repair_change':compare(oo,cc)}
        report['layers'].append(result)
        for label,geometry in [('source',aa),('previous',oo),('current',cc)]:
            args.output.with_name(args.output.stem+f'-inner{num}-{label}.wkb').write_bytes(geometry.wkb)
        print('LAYER',num,{k:v for k,v in result['repaired_comparison'].items()if not isinstance(v,list)},flush=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
