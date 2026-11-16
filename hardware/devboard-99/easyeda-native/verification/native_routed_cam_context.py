"""Exact source attribution for local CAM drills and permitted GND fanout.

No live EDA. This separates preserved footprint geometry from subsequent routing;
it never treats an arbitrary extra CAM hole/copper feature as acceptable.
"""
import json,math,zipfile
from pathlib import Path
from types import SimpleNamespace
from shapely.affinity import rotate,translate
from shapely.geometry import Point,GeometryCollection
from shapely.ops import unary_union
import native_source_geometry as fan
from native_exact_smd import exact_smd_pads

class RoutedContext:
    def __init__(self,source,state,archive):
        self.args=SimpleNamespace(source=Path(source),state=Path(state),archive=Path(archive))
        self.source,self.state,self.pads,holes,_,_=fan.load_inputs(self.args)
        exact={p["id"]:p for p in exact_smd_pads(self.source,self.state,self.args.archive)}
        self.pads=[exact.get(p["id"],p)for p in self.pads]
        self.items,self.holes,self.regions,self.board,self.unparsed=fan.source_geometry(self.source,self.pads,holes)
        with zipfile.ZipFile(archive) as z:
            name=next(n for n in z.namelist() if n.endswith('.epru'))
            libs,_,_=fan.archive_helper.merge_documents(z.read(name).decode())
        binding=fan.archive_helper.component_index(self.source)
        byid={h['id']:h for h in self.holes}
        # Native pin snapshots are rounded to0.1mil. Drill attribution instead
        # uses exact PCB component pose and native footprint source pad center.
        for c in self.state:
            body=self.source[('COMPONENT',c['id'])];lib=libs[binding[c['ref']]['footprint_uuid']]
            for (kind,ident),b in lib.items():
                if kind!='PAD' or not b.get('hole') or b['hole'].get('width',0)<=0:continue
                if (b.get('padOffsetX') or 0) or (b.get('padOffsetY') or 0):raise ValueError('Offset drill unsupported')
                h=b['hole'];g=fan.centered_shape(h['holeType'],h['width']*fan.MM,h['height']*fan.MM,
                      b.get('padAngle',0)+(b.get('relativeAngle',0)or 0),b['centerX']*fan.MM,b['centerY']*fan.MM)
                g=translate(rotate(g,body['angle'],origin=(0,0)),body['x']*fan.MM,body['y']*fan.MM)
                ident=c['id']+ident+'_hole'
                if ident not in byid:raise ValueError('Native drill missing from geometry inventory: '+ident)
                byid[ident]['g']=g
        self.holes=list(byid.values())
        self.vias={ident:b for (kind,ident),b in self.source.items() if kind=='VIA'}

    def drills_in_roi(self,pose,roi):
        out=[]
        for h in self.holes:
            g=pose.local(h['g'])
            if roi.covers(g.centroid):
                out.append({'id':h['id'],'geom':g,'plated':not h.get('npth',False),
                            'center_local_mm':[g.centroid.x,g.centroid.y]})
        return out

    def match_roi_drills(self,pose,roi,camrows,thermal_centers,tol=.0001):
        expected=self.drills_in_roi(pose,roi);unused=list(expected);errors=[];matched=[]
        for row in camrows:
            candidates=[h for h in unused if Point(row['center_local_mm']).distance(Point(h['center_local_mm']))<tol]
            if len(candidates)!=1:
                errors.append({'CAM_file':row['file'],'CAM_index':row['index'],'reason':'CAM drill lacks unique exact native source counterpart','source_candidates':len(candidates),'center_local_mm':row['center_local_mm']});continue
            h=candidates[0];unused.remove(h)
            delta=row['geom'].symmetric_difference(h['geom']).area
            haus=row['geom'].hausdorff_distance(h['geom'])
            if row['plated']!=h['plated'] or haus>tol or delta>h['geom'].length*tol:
                errors.append({'source_id':h['id'],'reason':'CAM/native hole shape or plating mismatch','hausdorff_mm':haus,'symmetric_difference_mm2':delta})
            thermal=any(Point(h['center_local_mm']).distance(Point(c))<tol for c in thermal_centers)
            viaid=h['id'].removesuffix('_hole');v=self.vias.get(viaid)
            if not thermal and v:
                # New via copper must remain clear of every SMD pad, including
                # same-net pads. Existing approved thermal vias are separately
                # matched by the explicit plan centers and not exempted by name.
                copper=fan.disk(v['centerX']*fan.MM,v['centerY']*fan.MM,v['viaDiameter']*fan.MM/2)
                gap=min(copper.distance(p['g']) for p in self.pads if len(p['layers'])==1)
                if gap<.15-.0001:errors.append({'source_id':viaid,'reason':'Additional via overlaps/approaches SMD pad; no new via-in-pad is permitted','minimum_smd_gap_mm':gap,'exact_native_source_geometry':True,'roundtrip_tolerance_mm':.0001})
            matched.append({'source_id':h['id'],'CAM_file':row['file'],'CAM_index':row['index'],'role':'planned_thermal_or_acoustic_hole' if thermal else 'additional_native_routing_or_component_drill','net':v.get('netName') if v else None,'hausdorff_mm':haus})
        if unused:errors.extend({'source_id':h['id'],'reason':'Native source drill missing from CAM','center_local_mm':h['center_local_mm']} for h in unused)
        return {'pass':not errors,'expected_source_count':len(expected),'actual_count':len(camrows),'matched':matched,'errors':errors}

    def ground_routing(self,pose,roi,layer=1):
        # Only explicit same-source GND lines/arcs/polys/vias can explain added
        # ring-exterior copper. A zone boundary or undecoded POURED cache cannot.
        selected=[o for o in self.items if o['net']=='GND' and layer in o['layers'] and
                  o['kind'] in ('line','arc','carc','poly','via') and o['g'].intersects(pose.world(roi))]
        return unary_union([pose.local(o['g']).intersection(roi) for o in selected]),[o['id']for o in selected]
