#!/usr/bin/env python3
"""Read RS-274X into geometry, preserving aperture-local and layer polarity.

Uses gerbonara for macro/arcs; curves are polygonized at <= 0.00005 mm.
Coordinates are native Gerber millimeters (Y up). No CAD/output is modified.
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

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('source',type=Path);ap.add_argument('migrated',type=Path);ap.add_argument('--cache',type=Path);ap.add_argument('--report',type=Path,required=True);args=ap.parse_args()
    a,am=read_geometry(args.source,args.cache);b,bm=read_geometry(args.migrated,args.cache)
    report={'source':am,'migrated':bm,'comparison':comparison(a,b),'limits':'Polygon comparison at documented curve tolerance; DRC/net connectivity and factory acceptance require separate checks.'}
    args.report.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report['comparison'].items()if not isinstance(v,list)}))
