"""Exact SMD copper from native library source and PCB pose, not API rounding."""
import zipfile,math
from shapely.geometry import box
from shapely.affinity import rotate,translate
import native_source_geometry as f

def exact_smd_pads(source,state,archive):
    with zipfile.ZipFile(archive)as z:
        names=[n for n in z.namelist()if n.endswith('.epru')]
        if len(names)!=1:raise ValueError('Expected one epru')
        libs,_,_=f.archive_helper.merge_documents(z.read(names[0]).decode())
    binding=f.archive_helper.component_index(source);result=[]
    for c in state:
        comp=source[('COMPONENT',c['id'])]
        if comp['layerId']!=1:raise ValueError('Exact SMD bottom-component transform unsupported')
        lib=libs[binding[c['ref']]['footprint_uuid']];pins={p['id']:p for p in c['pins']}
        for(kind,ident),b in lib.items():
            if kind!='PAD' or b['layerId']not in (1,2):continue
            if b.get('specialPad'):raise ValueError('Special per-layer SMD pad requires explicit support')
            p=pins[c['id']+ident];d=b['defaultPad'];typ=d['padType']
            if typ=='POLYGON':
                g=f.polygon(d['path'])
                # Native polygon path is already in footprint coordinates.
                # Confirm this transform against captured actual native geometry.
                sg=f.polygon(p['pad'][1])
            else:
                w,h=d['width']*f.MM,d['height']*f.MM
                if typ=='RECT':
                    percent=d.get('radius',0)or 0
                    if not 0<=percent<=50:raise ValueError('Unexpected RECT radius percentage')
                    rad=min(w,h)*percent/100
                    g=box(-w/2+rad,-h/2+rad,w/2-rad,h/2-rad).buffer(rad,quad_segs=256)if rad else box(-w/2,-h/2,w/2,h/2)
                    g=translate(rotate(g,b.get('padAngle',0),origin=(0,0)),b['centerX']*f.MM,b['centerY']*f.MM)
                else:g=f.centered_shape(typ,w,h,b.get('padAngle',0),b['centerX']*f.MM,b['centerY']*f.MM)
            g=translate(rotate(g,comp['angle'],origin=(0,0)),comp['x']*f.MM,comp['y']*f.MM)
            if typ=='POLYGON'and g.hausdorff_distance(sg)>.003:raise ValueError('Source polygon transform disagrees with actual native state: '+c['ref']+'.'+str(p['n']))
            result.append({'id':p['id'],'ref':c['ref'],'pin':p['n'],'net':p['net'],'layers':frozenset({b['layerId']}),'g':g,'kind':'pad','anchor':False})
    return result
