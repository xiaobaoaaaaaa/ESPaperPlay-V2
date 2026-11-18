#!/usr/bin/env python3
"""Read-only actual Gerber silkscreen, mask/drill/edge and attribution review."""
import argparse,collections,hashlib,json,math,zipfile
from pathlib import Path
from shapely.geometry import box,GeometryCollection,LineString,Point
from shapely.affinity import rotate,translate,scale
from shapely.ops import unary_union
from shapely.strtree import STRtree
HERE=Path(__file__).resolve().parent
DEFAULT_TEXT_BASELINE=HERE.parent/'audit/silkscreen/validated-glyph-baseline.json'
import native_cam_geometry as cg
import native_source_geometry as ng
from native_routed_cam_context import RoutedContext
from gerbonara.utils import approximate_arc
from gerbonara.graphic_objects import Arc
from gerbonara.apertures import CircleAperture

arc_strokes = []


def object_geometry(obj):
    if not isinstance(obj, Arc):
        return cg.object_geometry(obj)
    if not isinstance(obj.aperture, CircleAperture) or obj.aperture.hole_dia:
        raise ValueError('Expected a solid circular aperture for a Gerber arc stroke')
    q = obj.as_primitive(unit=cg.MM)
    centerline_radius = math.hypot(q.x1-q.cx, q.y1-q.cy)
    if centerline_radius == 0:
        if (q.x1, q.y1) != (q.x2, q.y2):
            raise ValueError('Gerber arc has a zero start radius and different endpoints')
        centerline = Point(q.x1, q.y1)
    else:
        points = list(approximate_arc(q.cx, q.cy, q.x1, q.y1, q.x2, q.y2,
                                      q.clockwise, max_error=0.000001))
        points[-1] = (q.x2, q.y2)
        centerline = LineString(points)
    # Sweep the circular aperture along the commanded arc. Gerbonara 1.6.2's
    # Arc.to_arc_poly can reverse an end cap or hit a zero-radius inner arc.
    arc_strokes.append({'center_mm':[q.cx,q.cy], 'start_mm':[q.x1,q.y1],
                        'end_mm':[q.x2,q.y2], 'stroke_mm':q.width})
    return centerline.buffer(q.width/2, quad_segs=256, cap_style='round')


def digest(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def union(objects):
    if all(o.polarity_dark for o in objects):return unary_union([object_geometry(o)for o in objects])
    g=GeometryCollection()
    for o in objects:
        q=object_geometry(o);g=g.union(q)if o.polarity_dark else g.difference(q)
    return g
def serial(g):return {'area_mm2':g.area,'bounds_mm':list(g.bounds)if not g.is_empty else None}


AREA_FLOOR_MM2 = 1e-8


def review_drill_geometry(ctx, cam, side_mask):
    """Retain every opening except a native plated via wholly under mask on this side."""
    native_via_holes = [hole['g'] for hole in ctx.holes
                        if hole['id'].removesuffix('_hole') in ctx.vias]
    tree = STRtree(native_via_holes)
    review = []
    for drill in cam.drills:
        hole = drill['geom_world']
        if drill['plated'] and not hole.intersects(side_mask):
            matches = tree.query(hole.centroid, predicate='intersects')
            if len(matches) == 1:
                native = native_via_holes[int(matches[0])]
                if hole.hausdorff_distance(native) <= cg.GEOMETRY_TOL * 2:
                    continue
        review.append(hole)
    return unary_union(review)


def actionable_intersections(ink, mask, review_drills, board):
    return {'mask_intersection': serial(ink.intersection(mask)),
            'non_tented_drill_intersection': serial(ink.intersection(review_drills)),
            'outside_board': serial(ink.difference(board))}


def has_intersection(findings):
    return any(item['area_mm2'] > AREA_FLOOR_MM2 for item in findings.values())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ['source','state','archive','zip','output']:ap.add_argument('--'+key,type=Path,required=True)
    ap.add_argument('--text-baseline-report',type=Path,default=DEFAULT_TEXT_BASELINE,help='Previously verified actual-text bounds for tight attribution after font/position/0|90 rotation changes; physical ink remains unmodified')
    ap.add_argument('--minimum-ink-height-mm',type=float,default=.8,help='Actual ink height review goal, independent of native nominal font size')
    a=ap.parse_args();out=a.output.parent;out.mkdir(parents=True,exist_ok=True)
    baseline={}
    if a.text_baseline_report:
        prior=json.loads(a.text_baseline_report.read_text())
        if prior.get('attribution_errors')or prior.get('designator_findings'):raise ValueError('Text baseline was not attribution/geometry-clean')
        baseline={r['ref']:r for r in prior['designators']}
        if any(not r['glyph_count_matches']for r in baseline.values()):raise ValueError('Text baseline glyph inventory invalid')
    ctx=RoutedContext(a.source,a.state,a.archive)
    cg.LAYERS.update({'F.Silk':'.GTO','B.Silk':'.GBO'})
    cam=cg.Cam(a.zip,out/(a.output.stem+'-extracted'))
    silk={};parts={};indexes={}
    for layer in ['F.Silk','B.Silk']:
        layerparts=[object_geometry(o)for o in cam.layers[layer].objects]
        parts[layer]=layerparts;indexes[layer]=STRtree(layerparts)
        silk[layer]=unary_union(layerparts)if all(o.polarity_dark for o in cam.layers[layer].objects)else union(cam.layers[layer].objects)
        print(layer,len(layerparts),'objects',flush=True)
    mask={side:union(cam.layers[side+'.Mask'].objects)for side in ['F','B']}
    drills=unary_union([d['geom_world']for d in cam.drills])
    review_drills = {side: review_drill_geometry(ctx, cam, mask[side]) for side in mask}
    def silk_at(layer,region):
        if all(o.polarity_dark for o in cam.layers[layer].objects):
            return unary_union([parts[layer][int(i)]for i in indexes[layer].query(region)]).intersection(region)
        return silk[layer].intersection(region)
    with zipfile.ZipFile(a.archive)as z:
        libraries,_,_=ng.archive_helper.merge_documents(z.read(next(n for n in z.namelist()if n.endswith('.epru'))).decode())
    bindings=ng.archive_helper.component_index(ctx.source)
    body={};body_records=[];silk_overrides=[]
    for component in ctx.state:
        ref=component['ref'];pose=ctx.source[('COMPONENT',component['id'])]
        for (kind,ident),b in libraries[bindings[ref]['footprint_uuid']].items():
            if not isinstance(b,dict)or b.get('layerId')not in[3,4]or kind=='ATTR':continue
            override=ctx.source.get((kind,component['id']+ident))
            if override is not None:
                if override.get('layerId')not in[3,4]or override.get('netName')not in['',None]:
                    raise ValueError(('Unexpected native silk override layer/net',ref,ident))
                b=override;silk_overrides.append({'ref':ref,'id':component['id']+ident,'kind':kind,'coordinate_basis':'observed PCB absolute world coordinates'})
            if kind=='POLY':g=ng.path_line(b['path']).buffer(b['width']*ng.MM/2,quad_segs=32)
            elif kind=='FILL':g=ng.polygon(b['path'])
            else:raise ValueError(('Unsupported footprint silk',ref,kind,ident))
            if override is None:g=translate(rotate(g,pose['angle'],origin=(0,0)),pose['x']*ng.MM,pose['y']*ng.MM)
            side='F'if b['layerId']==3 else'B';key=(ref,side)
            body.setdefault(key,[]).append(g)
            body_records.append({'ref':ref,'id':ident,'kind':kind,'side':side,'g':g})
    body={key:unary_union(gs)for key,gs in body.items()}
    textrows=[];textgeom=[];attribution_errors=[];assigned=collections.defaultdict(set)
    visible=[]
    for (kind,ident),b in ctx.source.items():
        if kind!='ATTR'or b.get('layerId')not in[3,4]or not b.get('valueVisible'):continue
        if b.get('key')!='Designator':
            attribution_errors.append({'kind':'OTHER_VISIBLE_TEXT_REQUIRES_REVIEW','id':ident,'value':b.get('value')});continue
        if b.get('origin')!='CENTER_MIDDLE'or b.get('mirror')or b.get('reverse')or b.get('angle')not in[0,90]:
            raise ValueError(('Unsupported text style',ident,b))
        ref=b['value'];font=b['fontSize']*ng.MM;x=b['x']*ng.MM;y=b['y']*ng.MM
        if a.text_baseline_report:
            q=baseline.get(ref)
            if not q or q['attribute_id']!=ident or b.get('fontFamily')!='default':raise ValueError(('Unmatched text baseline',ref,ident))
            ox,oy=q['native_position_mm'];factor=font/q['font_mm']
            envelope=translate(box(*q['actual_ink']['bounds_mm']),-ox,-oy)
            envelope=scale(envelope,xfact=factor,yfact=factor,origin=(0,0))
            # Font centreline scales; stroke is separately specified. When
            # current stroke exceeds the scaled old stroke, include exactly
            # that half-width increment, plus CAM coordinate quantization.
            extra=max(0,(b['strokeWidth']*ng.MM-factor*q['stroke_mm'])/2)
            envelope=envelope.buffer(extra+cg.GEOMETRY_TOL,join_style=2)
            envelope=translate(rotate(envelope,b['angle']-q['rotation'],origin=(0,0)),x,y)
        else:
            envelope=box(-(.72*len(ref)*font+.2)/2,-(font+.2)/2,(.72*len(ref)*font+.2)/2,(font+.2)/2)
            envelope=translate(rotate(envelope,b['angle'],origin=(0,0)),x,y)
        side='F'if b['layerId']==3 else'B';layer=side+'.Silk';hits=[]
        for index in indexes[layer].query(envelope):
            index=int(index);g=parts[layer][index]
            if g.intersection(envelope).area>1e-9:
                hits.append(index)
                if not envelope.buffer(cg.GEOMETRY_TOL).covers(g):attribution_errors.append({'kind':'TEXT_ENVELOPE_PARTIAL_CAM_PRIMITIVE','ref':ref,'CAM_object':index})
        g=unary_union([parts[layer][i]for i in hits]);textgeom.append(g);visible.append(ref)
        for i in hits:
            if i in assigned[layer]:attribution_errors.append({'kind':'CAM_PRIMITIVE_ASSIGNED_TO_MULTIPLE_LABELS','ref':ref,'CAM_object':i})
        assigned[layer].update(hits)
        # This tiny merge is ONLY for detecting separated character components;
        # actual mask/edge/hole intersections below use unchanged Gerber ink.
        glyphs=cg.polygons(g.buffer(cg.GEOMETRY_TOL/2))
        glyph_count=len(glyphs)
        bb=g.bounds;inkheight=0.0 if g.is_empty else((bb[3]-bb[1])if b['angle']==0 else(bb[2]-bb[0]))
        row={'ref':ref,'attribute_id':ident,'side':side,'font_mm':font,'stroke_mm':b['strokeWidth']*ng.MM,
             'actual_ink_height_mm':inkheight,'actual_ink_height_goal_mm':a.minimum_ink_height_mm,
             'actual_ink_height_meets_goal':inkheight>=a.minimum_ink_height_mm,
             'attribution_envelope_mm':list(envelope.bounds),'attribution_mode':'verified_old_actual_ink_scaled'if a.text_baseline_report else'conservative_nominal_box',
             'native_position_mm':[x,y],'rotation':b['angle'],'CAM_object_count':len(hits),
             'expected_character_count':len(ref),'actual_disconnected_glyph_count':glyph_count,
             'glyph_count_matches':glyph_count==len(ref),'actual_ink':serial(g),
             'mask_intersection':serial(g.intersection(mask[side])),'drill_intersection':serial(g.intersection(drills)),
             'outside_board':serial(g.difference(ctx.board)),'minimum_mask_distance_mm':g.distance(mask[side])if not g.is_empty else None,
             'minimum_drill_distance_mm':g.distance(drills)if not g.is_empty else None,
             'minimum_board_edge_distance_mm':g.distance(ctx.board.boundary)if not g.is_empty else None}
        textrows.append(row)
    refset={c['ref']for c in ctx.state}
    if set(visible)!=refset or len(visible)!=len(refset):attribution_errors.append({'kind':'VISIBLE_DESIGNATOR_INVENTORY','missing':sorted(refset-set(visible)),'extra':sorted(set(visible)-refset),'count':len(visible)})
    bodyrows=[]
    covered_outline_rows=[]
    for (ref,side),expected in sorted(body.items()):
        actual=silk_at(side+'.Silk',expected.buffer(cg.GEOMETRY_TOL))
        violations = actionable_intersections(actual, mask[side], review_drills[side], ctx.board)
        issues = {**violations, 'drill_intersection':serial(actual.intersection(drills)),
                  'mask_open_drill_intersection':serial(actual.intersection(drills).intersection(mask[side])),
                  'drill_projection_under_mask':serial(actual.intersection(drills).difference(mask[side]))}
        if not has_intersection(issues):
            continue
        row = {'ref':ref, 'side':side, 'attribution':'existing_native_library_outline_or_marker',
               'minimum_repair_primitive_ids':[], **issues}
        if not has_intersection(violations):
            covered_outline_rows.append(row)
            continue
        for rr in body_records:
            if rr['ref'] != ref or rr['side'] != side:
                continue
            local = silk_at(side+'.Silk', rr['g'].buffer(cg.GEOMETRY_TOL))
            local_violations = actionable_intersections(local, mask[side], review_drills[side], ctx.board)
            if has_intersection(local_violations):
                row['minimum_repair_primitive_ids'].append({'footprint_primitive':rr['id'],
                                                            'kind':rr['kind'], **local_violations})
        bodyrows.append(row)
    # Ref-level footprint outline attribution deliberately does not guess that
    # a colliding round dot is electrically pin 1; source pad positions and
    # assembly drawings must settle orientation. Small visible markers and
    # their coordinates are retained for visual review.
    markers=[]
    for r in body_records:
        if r['kind']!='FILL':continue
        actual=silk_at(r['side']+'.Silk',r['g'].buffer(cg.GEOMETRY_TOL))
        markers.append({'ref':r['ref'],'footprint_primitive':r['id'],'kind':'native_filled_marker','side':r['side'],
                        'actual_ink':serial(actual),'mask_intersection':serial(actual.intersection(mask[r['side']])),
                        'expected_center_mm':[r['g'].centroid.x,r['g'].centroid.y]})
    summary={}
    layer_findings={}
    for side in ['F','B']:
        ink=silk[side+'.Silk']
        violations = actionable_intersections(ink, mask[side], review_drills[side], ctx.board)
        if has_intersection(violations):
            layer_findings[side] = violations
        summary[side]={'CAM_object_count':len(parts[side+'.Silk']),'ink_area_mm2':ink.area,
            **violations,'drill_intersection':serial(ink.intersection(drills)),
            'mask_open_drill_intersection':serial(ink.intersection(drills).intersection(mask[side])),
            'drill_projection_under_mask':serial(ink.intersection(drills).difference(mask[side])),
            'outside_board':serial(ink.difference(ctx.board))}
    badtext=[r for r in textrows if not r['glyph_count_matches']or any(r[k]['area_mm2']>1e-8 for k in['mask_intersection','drill_intersection','outside_board'])]
    fontreview=[{'ref':r['ref'],'nominal_font_mm':r['font_mm'],'actual_ink_height_mm':r['actual_ink_height_mm'],
                 'actual_ink_height_goal_mm':a.minimum_ink_height_mm}for r in textrows if not r['actual_ink_height_meets_goal']]
    report={'status':'SILKSCREEN_REVIEW_REQUIRED'if layer_findings or bodyrows or badtext or attribution_errors or fontreview else'ACTUAL_SILKSCREEN_GEOMETRY_SCREEN_PASS',
            'inputs':{k:digest(getattr(a,k))for k in['source','state','archive','zip','text_baseline_report']if getattr(a,k,None)},'checker':digest(Path(__file__).resolve()),
            'layer_summary':summary,'layer_findings':layer_findings,
            'covered_via_outline_projections_only':covered_outline_rows,'designators':textrows,'designator_findings':badtext,'library_outline_findings':bodyrows,
            'actual_ink_height_review_items':fontreview,'native_filled_markers':markers,'attribution_errors':attribution_errors,
            'native_instance_silk_overrides':silk_overrides,'circular_aperture_arc_strokes':arc_strokes,
            'limits':['Whole-layer positive-area mask, outside-board or non-tented drill intersections require review even for unassigned board artwork. Only plated native VIA drill matches wholly clear of actual mask apertures on the corresponding side are informational for outline projection. Hole/ink overlap under labels is still reported for readability.',
                      'Archive footprint geometry is used for attribution; board-level designator style/position is read from the newer source. Old archive text placement is not asserted current.',
                      'Character component counts detect missing/merged glyphs but are not OCR. Actual characters and pin-1/polarity meaning require visual review against source/assembly data.',
                      'Positive-area intersections are reported without silkscreen clearance threshold substitution. Factory clipping/ink registration/readability is not guaranteed.',
                      'Do not alter copper, solder-mask or paste apertures to cure an outline collision; adjust or remove silk only.']}
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'designators':len(textrows),'designator_findings':len(badtext),
                     'library_outline_findings':len(bodyrows),'attribution_errors':attribution_errors,'layers':summary},ensure_ascii=False),flush=True)
    # An unresolved outline review is not a geometry-screen PASS. This exit
    # status does not classify covered-hole projections as electrical DRC errors.
    return int(report['status'] != 'ACTUAL_SILKSCREEN_GEOMETRY_SCREEN_PASS')


if __name__=='__main__':raise SystemExit(main())
