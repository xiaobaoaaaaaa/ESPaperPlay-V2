"""Read-only native Gerber/Excellon geometry helpers; all coordinates mm, +Y up.

No pcbnew, no CAD execution, no source mutation. Reuses the established project's
Gerbonara primitive-polarity method, with local aperture clear/dark composition.
"""
import hashlib
import json
import math
import re
import sys
import zipfile
from pathlib import Path

# Dependencies come from the active Python environment or an explicit
# PYTHONPATH (see README). No ignored build/ directory is required by this copy.
from gerbonara import GerberFile, ExcellonFile
from gerbonara.utils import MM
from shapely.geometry import Polygon, Point, GeometryCollection, box
from shapely.ops import unary_union
from shapely.affinity import translate, rotate

ARC_ERROR = .00001
GEOMETRY_TOL = .00006
LAYERS = {'F.Cu':'.GTL','B.Cu':'.GBL','In1.Cu':'.G1','In2.Cu':'.G2',
          'F.Mask':'.GTS','B.Mask':'.GBS','F.Paste':'.GTP','B.Paste':'.GBP'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def polygons(g):
    if g.is_empty:
        return []
    if g.geom_type == 'Polygon':
        return [g]
    return [p for q in g.geoms for p in polygons(q)]


def object_geometry(obj):
    shape = GeometryCollection()
    for primitive in obj.to_primitives(MM):
        coords = primitive.to_arc_poly().approximate_arcs(ARC_ERROR).outline
        if len(coords) < 3:
            continue
        part = Polygon(coords).buffer(0)
        shape = shape.union(part) if primitive.polarity_dark == obj.polarity_dark else shape.difference(part)
    return shape


def rounded_rect(x,y,w,h,r=0):
    if not r:
        return box(x-w/2,y-h/2,x+w/2,y+h/2)
    return box(x-w/2+r,y-h/2+r,x+w/2-r,y+h/2-r).buffer(r,quad_segs=512)


def extrude(poly,dx,dy):
    pieces = [translate(poly,xoff=dx,yoff=dy),translate(poly,xoff=-dx,yoff=-dy)]
    for polygon in polygons(poly):
        for ring in [polygon.exterior,*polygon.interiors]:
            coords=list(ring.coords)
            for (ax,ay),(bx,by) in zip(coords,coords[1:]):
                strip=Polygon([(ax-dx,ay-dy),(bx-dx,by-dy),(bx+dx,by+dy),(ax+dx,ay+dy)])
                if strip.area:pieces.append(strip)
    return unary_union(pieces)


class Pose:
    def __init__(self,component):
        self.ref=component['ref'];self.x=component['x']*.0254;self.y=component['y']*.0254
        self.angle=component['rotation'];self.component=component
        assert component.get('layer',1)==1,'Only top-side parts supported'

    def world(self,g):
        return translate(rotate(g,self.angle,origin=(0,0)),xoff=self.x,yoff=self.y)

    def local(self,g):
        return rotate(translate(g,xoff=-self.x,yoff=-self.y),-self.angle,origin=(0,0))

    def detail(self):
        return {'origin_world_mm':[self.x,self.y],'rotation_deg':self.angle,'source':'Actual native component snapshot; no Y flip'}


def poses(path):
    data=json.loads(Path(path).read_text())
    if isinstance(data,dict):data=data.get('result',data)
    if isinstance(data,dict):data=data.get('components',data)
    assert isinstance(data,list),'Expected native component list'
    return {c['ref']:Pose(c) for c in data}


class Cam:
    def __init__(self,archive,directory):
        self.archive=Path(archive);self.directory=Path(directory);self.layers={};self.drills=[]
        self.stats={};self.files={};self._cache={};self.drill_normalizations=[];self.duplicate_drill_views=[]
        with zipfile.ZipFile(self.archive) as z:
            for info in z.infolist():
                if info.is_dir():continue
                name=Path(info.filename)
                assert not name.is_absolute() and '..' not in name.parts,'Unsafe ZIP path'
                target=self.directory/name;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(z.read(info));self.files[info.filename]=sha(target)
                ext=target.suffix.upper()
                layer=next((k for k,v in LAYERS.items() if ext==v),None)
                if layer:
                    assert layer not in self.layers,('Duplicate layer',layer)
                    self.layers[layer]=GerberFile.open(target)
                    self.stats[layer]={'file':info.filename,'objects':len(self.layers[layer].objects)}
                elif ext in ('.DRL','.XLN'):
                    plated='NPTH' not in name.name.upper()
                    # Gerbonara 1.6 lacks native EasyEDA's G85 canned slot. Expand
                    # only the observed explicit XY/XY form into equivalent
                    # straight routing in memory, without rounding coordinates.
                    lines=[];converted=0
                    for line in target.read_text().splitlines():
                        if 'G85' in line:
                            m=re.fullmatch(r'(X[-+0-9.]+Y[-+0-9.]+)G85(X[-+0-9.]+Y[-+0-9.]+)',line)
                            assert m,('Unsupported G85 syntax',line)
                            lines.extend(['G00'+m[1],'M15','G01'+m[2],'M16','G05']);converted+=1
                        else:lines.append(line)
                    drill=ExcellonFile.from_string('\n'.join(lines),filename=str(target),plated=plated)
                    if converted:self.drill_normalizations.append({'file':info.filename,'explicit_G85_slots_expanded_in_memory':converted})
                    for i,obj in enumerate(drill.objects):
                        geom=object_geometry(obj)
                        self.drills.append({'file':info.filename,'index':i,'plated':plated,'geom_world':geom,
                                            'center_world_mm':[geom.centroid.x,geom.centroid.y],
                                            'diameter_mm':getattr(getattr(obj,'aperture',None),'diameter',None),
                                            'class':type(obj).__name__})
        missing=set(LAYERS)-{'B.Paste'}-set(self.layers)
        assert not missing,('Missing required CAM layers',missing)
        # EasyEDA can emit both a complete PTH drill file and its VIA-only view.
        # Remove a subsidiary-view hit only if an identical complete-file hit
        # is observed; retain same-file duplicates and unknown-file duplicates.
        unique=[]
        for d in self.drills:
            is_view=Path(d['file']).name.upper()=='DRILL_PTH_THROUGH_VIA.DRL'
            same=[q for q in self.drills if Path(q['file']).name.upper()=='DRILL_PTH_THROUGH.DRL'
                  and q['plated']==d['plated'] and q['class']==d['class'] and q['geom_world'].equals_exact(d['geom_world'],1e-10)] if is_view else []
            if len(same)==1:self.duplicate_drill_views.append({'view_file':d['file'],'view_index':d['index'],'authoritative_file':same[0]['file'],'authoritative_index':same[0]['index'],'center_world_mm':d['center_world_mm']})
            else:unique.append(d)
        self.drills=unique

    def roi(self,layer,pose,local_roi):
        if layer not in self.layers:
            return GeometryCollection(),[]
        world_roi=pose.world(local_roi);whole=GeometryCollection();records=[]
        for i,obj in enumerate(self.layers[layer].objects):
            bb=obj.bounding_box(MM)
            if bb is None:continue
            (x0,y0),(x1,y1)=bb
            if not world_roi.intersects(box(x0,y0,x1,y1)):continue
            key=(layer,i)
            if key not in self._cache:self._cache[key]=object_geometry(obj)
            local=pose.local(self._cache[key]).intersection(local_roi)
            whole=whole.union(local) if obj.polarity_dark else whole.difference(local)
            records.append({'index':i,'dark':bool(obj.polarity_dark),'class':type(obj).__name__,'geom':local})
        return whole,records

    def local_drills(self,pose,local_roi):
        rows=[]
        for d in self.drills:
            geom=pose.local(d['geom_world'])
            if not local_roi.covers(geom.centroid):continue
            rows.append({**{k:v for k,v in d.items() if k!='geom_world'},'geom':geom,
                         'center_local_mm':[geom.centroid.x,geom.centroid.y],
                         'diameter_measured_mm':max(geom.bounds[2]-geom.bounds[0],geom.bounds[3]-geom.bounds[1])})
        return rows


def serial_drills(rows):
    return [{k:v for k,v in r.items() if k!='geom'} for r in rows]


def match_objects(records,expected,tol=GEOMETRY_TOL):
    candidates=[r for r in records if r['dark'] and r['geom'].buffer(tol).covers(expected.representative_point())]
    if not candidates:return {'pass':False,'reason':'No dark CAM primitive at expected position'},GeometryCollection()
    best=min(candidates,key=lambda r:r['geom'].symmetric_difference(expected).area)
    actual=best['geom'];diff=actual.symmetric_difference(expected).area;haus=actual.hausdorff_distance(expected)
    ok=diff<=expected.length*tol and haus<=tol*2
    return {'pass':ok,'CAM_object':best['index'],'class':best['class'],'area_mm2':actual.area,
            'bounds_local_mm':list(actual.bounds),'symmetric_difference_mm2':diff,'hausdorff_mm':haus},actual


def exact_union_metrics(actual,expected,tol=GEOMETRY_TOL):
    diff=actual.symmetric_difference(expected).area
    haus=actual.hausdorff_distance(expected) if not actual.is_empty and not expected.is_empty else None
    ok=diff<=max(expected.length*tol,1e-8) and haus is not None and haus<=2*tol
    return {'pass':ok,'actual_area_mm2':actual.area,'expected_area_mm2':expected.area,
            'components':len(polygons(actual)),'symmetric_difference_mm2':diff,'hausdorff_mm':haus}
