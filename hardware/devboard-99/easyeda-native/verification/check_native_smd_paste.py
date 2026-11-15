#!/usr/bin/env python3
"""Screen every fitted native SMD pad for actual CAM paste coverage, read-only.

J501 is excluded from this generic screen and has a separate CAM review. DNP, plated
through-hole pads and U301's intentional central no-paste EP are excluded.
"""
import argparse
import collections
import json
import tempfile
from pathlib import Path
from native_cam_geometry import *
from shapely.strtree import STRtree


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--zip',type=Path,required=True);ap.add_argument('--state',type=Path,required=True)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--report',type=Path,required=True)
    a=ap.parse_args();inputs={str(p):sha(p) for p in [a.zip,a.state,a.source]}
    state=json.loads(a.state.read_text());components={}
    for line in a.source.read_text().splitlines():
        h,b=line.removesuffix('|').split('||',1);h=json.loads(h);b=json.loads(b)
        if h['type']=='COMPONENT':components[h['id']]=b
    checked=[];excluded=[];missing=[];low=[];unresolved=[]
    with tempfile.TemporaryDirectory(prefix='native-smd-paste-read-') as td:
        cam=Cam(a.zip,td);copper_by_layer={};paste_by_layer={}
        for L,PL in [('F.Cu','F.Paste'),('B.Cu','B.Paste')]:
            cu=[];indices=[]
            for i,o in enumerate(cam.layers[L].objects):
                if not o.polarity_dark:continue
                geom=object_geometry(o)
                if not geom.is_empty and geom.area>0:cu.append(geom);indices.append(i)
            copper_by_layer[L]=(cu,indices,STRtree(cu))
            whole=GeometryCollection();pending=[]
            for o in cam.layers[PL].objects if PL in cam.layers else []:
                geom=object_geometry(o)
                if o.polarity_dark:pending.append(geom)
                else:whole=whole.union(unary_union(pending)).difference(geom);pending=[]
            paste_by_layer[L]=whole.union(unary_union(pending))
        for c in state:
            assert c['id'] in components,('Missing assembly metadata',c['ref'])
            attrs=components[c['id']].get('attrs',{})
            is_dnp=str(attrs.get('DNP','')).lower() in ('true','1','yes') or str(attrs.get('AssemblyStatus','')).upper()=='DNP'
            for p in c['pins']:
                base={'ref':c['ref'],'number':p['n'],'native_pin_id':p['id'],'layer':p['layer']}
                if is_dnp:excluded.append({**base,'reason':'DNP from current native COMPONENT attrs'});continue
                if p['layer']==12:excluded.append({**base,'reason':'MULTI-layer through-hole pad; not SMD'});continue
                if c['ref']=='J501':excluded.append({**base,'reason':'J501_EXCLUDED_SEPARATE_CAM_REVIEW_REQUIRED'});continue
                if c['ref']=='U301' and p['n']=='41':excluded.append({**base,'reason':'User project intentional U301 central zero-paste'});continue
                if p['layer'] not in (1,2):excluded.append({**base,'reason':'Not an external-layer SMD pad'});continue
                L='F.Cu' if p['layer']==1 else 'B.Cu';cu,indices,tree=copper_by_layer[L]
                pt=Point(p['x']*.0254,p['y']*.0254);shape=p['pad'];expected_area=None
                if shape[0] in ('RECT','OVAL','ELLIPSE'):
                    expected_area=shape[1]*shape[2]*.0254**2
                    if shape[0]=='ELLIPSE':expected_area*=math.pi/4
                    if shape[0]=='OVAL':expected_area-=(4-math.pi)*(min(shape[1],shape[2])*.0254/2)**2
                candidates=[int(i) for i in tree.query(pt.buffer(.004)) if cu[int(i)].buffer(.004).covers(pt)]
                if not candidates:
                    unresolved.append({**base,'reason':'No actual copper primitive at native pin query point'});continue
                if expected_area:
                    i=min(candidates,key=lambda i:abs(cu[i].area-expected_area))
                else:i=min(candidates,key=lambda i:cu[i].area)
                geometry=cu[i];overlap=geometry.intersection(paste_by_layer[L]);ratio=overlap.area/geometry.area
                row={**base,'CAM_copper_object':indices[i],'copper_area_mm2':geometry.area,'paste_intersection_mm2':overlap.area,'coverage_percent':ratio*100,
                     'actual_copper_bounds_world_mm':list(geometry.bounds)}
                checked.append(row)
                if overlap.area<1e-7:missing.append(row)
                elif ratio<.25:low.append(row)
        assert all(sha(Path(p))==v for p,v in inputs.items())
        result={'status':'NO_MISSING_PASTE_FOUND_IN_CHECKED_SCOPE_J501_SEPARATE_REVIEW' if not missing and not low and not unresolved else 'REQUIRES_REVIEW',
                'scope':'Presence/low-coverage screen of fitted numbered native external-layer SMD pads using actual Gerber copper primitives and paste union. Not final stencil release; J501 excluded and requires its separate CAM review.',
                'input_hashes':inputs,'script_sha256':sha(Path(__file__)),'component_count':len(state),
                'checked_SMD_pad_instances':len(checked),'excluded_pad_instances':len(excluded),'excluded_counts':dict(collections.Counter(r['reason'] for r in excluded)),
                'missing_paste_count':len(missing),'missing_paste':missing,'low_coverage_below25percent':low,'unresolved_copper_matches':unresolved,
                'checked':checked,'excluded':excluded,'J501_status':'NOT_EVALUATED_HERE_USE_SEPARATE_CAM_REVIEW',
                'method':'Native pin centers are rounded ~0.1mil, so locate actual copper primitives within0.004mm. Select by native pad approximate area when available; measure paste intersection on actual CAM copper geometry. Polygon microphone sectors also checked individually. No automatic-paste metadata is trusted.',
                'limits':['This is paste presence/coverage screening, not aperture shape qualification for every generic component. Five critical corrected components have a separate exact-geometry report.',
                          'DNP exclusion is from current native source attributes; PTH exclusion uses MULTI layer, not the known inaccurate API hole-diameter getter.',
                          'No conclusion for J501 or production readiness; routing/planes remain incomplete.']}
    a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','component_count','checked_SMD_pad_instances','excluded_counts','missing_paste_count','low_coverage_below25percent','unresolved_copper_matches']},ensure_ascii=False,indent=2))
    return bool(missing or low or unresolved)


if __name__=='__main__':raise SystemExit(main())
