#!/usr/bin/env python3
"""Render actual CAM solids, retaining drill openings; native Gerber millimeters."""
from pathlib import Path
import argparse,sys,html
import cairosvg
from gerbonara import ExcellonFile
from gerbonara.utils import MM
from shapely.geometry import box
from shapely.ops import unary_union
from cam_geometry import read_geometry,object_geometry

def path(g):
    if g.is_empty:return ''
    ps=[g] if g.geom_type=='Polygon' else list(g.geoms)
    d=[]
    for p in ps:
        if p.geom_type!='Polygon':continue
        for ring in [p.exterior,*p.interiors]:
            pts=list(ring.coords);d.append('M'+' L'.join(f'{x:.5f},{y:.5f}'for x,y in pts)+' Z')
    return ' '.join(d)
def render(eda,out,cache):
    out.mkdir(parents=True,exist_ok=True)
    holes=unary_union([object_geometry(o) for n in ['Drill_PTH_Through.DRL','Drill_NPTH_Through.DRL']for o in ExcellonFile.open(eda/n).objects])
    for side,cu,mask,silk in [('top','GTL','GTS','GTO'),('bottom','GBL','GBS','GBO')]:
        a=read_geometry(next(eda.glob('*.'+cu)),cache)[0].difference(holes)
        m=read_geometry(next(eda.glob('*.'+mask)),cache)[0]
        s=read_geometry(next(eda.glob('*.'+silk)),cache)[0].difference(holes)
        board=box(50,-160,210,-50).difference(holes)
        layers=[(board,'#173e38'),(a,'#587044'),(a.intersection(m),'#e8c36a'),(s,'#f0f1df')]
        transform='translate(0,-210) scale(1,-1)' if side=='top' else 'translate(260,-210) scale(-1,-1)'
        svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="45 -165 170 120" width="2040" height="1440"><rect x="45" y="-165" width="170" height="120" fill="#13202b"/>'
        svg+=f'<g transform="{transform}" fill-rule="evenodd">'
        svg+=''.join(f'<path fill="{c}" d="{path(g)}"/>'for g,c in layers)+'</g></svg>'
        (out/f'cam-{side}.svg').write_text(svg)
        cairosvg.svg2png(bytestring=svg.encode(),write_to=str(out/f'cam-{side}.png'))
        print(side,'rendered')
    for n in [1,2]:
        g=read_geometry(eda/f'Gerber_InnerLayer{n}.G{n}',cache)[0].difference(holes)
        svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="45 -165 170 120" width="2040" height="1440"><rect x="45" y="-165" width="170" height="120" fill="#13202b"/>'
        svg+=f'<g transform="translate(0,-210) scale(1,-1)" fill-rule="evenodd"><path fill="#beab69" d="{path(g)}"/></g></svg>'
        (out/f'cam-inner{n}.svg').write_text(svg);cairosvg.svg2png(bytestring=svg.encode(),write_to=str(out/f'cam-inner{n}.png'))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('eda',type=Path);p.add_argument('output',type=Path);p.add_argument('--cache',type=Path);a=p.parse_args();render(a.eda,a.output,a.cache)
