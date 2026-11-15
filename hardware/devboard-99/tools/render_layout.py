#!/usr/bin/env python3
"""Export native KiCad placement views without changing the design.

Only a temporary plot copy suppresses duplicate F.Fab reference strings. The
formal PCB, all pad/footprint geometry, and its reference fields remain intact.
"""
from pathlib import Path
import argparse,subprocess,re,hashlib,tempfile
import pcbnew as P
import cairosvg

def run(*args):subprocess.run(args,check=True)
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--board',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();a.output.mkdir(exist_ok=True,parents=True)
 before=hashlib.sha256(a.board.read_bytes()).hexdigest()
 def export(board,name,layers,bw=False,dnp=False):
  out=a.output/(name+'.svg');args=['kicad-cli','pcb','export','svg','--layers',layers,'--mode-single','--page-size-mode','2','--exclude-drawing-sheet','--output',str(out)]
  if bw:args.append('--black-and-white')
  if dnp:args.append('--crossout-DNP-footprints-on-fab-layers')
  run(*args,str(board));return out
 front=export(a.board,'front-layout','F.Cu,F.Silkscreen,Edge.Cuts')
 with tempfile.TemporaryDirectory(prefix='espaperplay-assembly-')as temp:
  b=P.LoadBoard(str(a.board))
  for f in b.GetFootprints():
   if not f.Reference().IsVisible():continue # retain the two assembly-only designators
   for g in f.GraphicalItems():
    if g.GetLayer()==P.F_Fab and hasattr(g,'GetText')and g.GetText()in ['${REFERENCE}','${VALUE}',f.GetReference(),f.GetValue()]:g.SetLayer(P.User_9)
  copy=Path(temp)/'assembly-view.kicad_pcb';P.SaveBoard(str(copy),b)
  assembly=export(copy,'assembly-layout','F.Fab,F.Silkscreen,Edge.Cuts',True,True)
 access=export(a.board,'access-layout','F.Fab,F.CrtYd,Edge.Cuts,Dwgs.User',True)
 # Native geometry remains unchanged: widen viewport to include its off-board drawings.
 s=access.read_text();s=re.sub(r'width="[^"]+mm" height="[^"]+mm" viewBox="[^"]+"','width="132mm" height="145mm" viewBox="-14 -27 132 145"',s,count=1);access.write_text(s)
 for p,bg,w,h in [(front,'#111a18',1600,1600),(assembly,'white',1600,1600),(access,'white',1584,1740)]:
  cairosvg.svg2png(url=str(p),write_to=str(p.with_suffix('.png')),output_width=w,output_height=h,background_color=bg)
 assert hashlib.sha256(a.board.read_bytes()).hexdigest()==before,'Source PCB changed during render'
if __name__=='__main__':main()
