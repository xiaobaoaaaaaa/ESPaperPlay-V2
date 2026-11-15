#!/usr/bin/env python3
"""Read-only operation access envelopes for the compact board; engineering margins."""
from pathlib import Path
import argparse,json,hashlib
import pcbnew as P
from shapely.geometry import Polygon,box,Point
from shapely.ops import unary_union

def court(f):
 s=f.GetCourtyard(P.F_CrtYd);parts=[]
 for i in range(s.OutlineCount()):
  l=s.COutline(i);parts.append(Polygon([(l.CPoint(j).x/1e6,l.CPoint(j).y/1e6)for j in range(l.PointCount())]))
 return unary_union(parts)
def main():
 p=argparse.ArgumentParser();p.add_argument('--board',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();b=P.LoadBoard(str(a.board));fps={f.GetReference():f for f in b.GetFootprints()};g={r:court(f)for r,f in fps.items()};ev=[]
 expected_angles={'J501':180,'J701':90,'J406':90,'J601':0,'J102':90,'J103':90,'J801':270,**{r:0 for r in ['SW301','SW302','SW303','SW304','SW305']}}
 for r,angle in expected_angles.items():
  actual=fps[r].GetOrientationDegrees()%360
  if abs(actual-angle)>1e-6:raise ValueError(f'{r}: envelope assumes {angle} degrees; board has {actual} degrees')
 def rect(name,ref,bb,purpose):ev.append({'name':name,'reference':ref,'shape':'rect','bounds_mm':bb,'purpose':purpose})
 def circle(name,ref,c,r,purpose):ev.append({'name':name,'reference':ref,'shape':'circle','center_mm':c,'radius_mm':r,'purpose':purpose})
 def pos(r):q=fps[r].GetPosition();return[q.x/1e6,q.y/1e6]
 # Socket shell/courtyard is source geometry; cable/grip/lock dimensions below are engineering allowances.
 x,y=pos('J501');rect('USB_PLUG_AND_STRAIGHT_EXIT','J501',[x-7,-16,x+7,y-3.675],'14mm wide plug/strain-relief candidate, straight out top; reserve away from MCU RF courtyard')
 x,y=pos('J701');rect('SD_INSERT_EJECT','J701',[x+8.125,y-6.5,116,y+7.5],'18mm outboard insertion/ejection access; includes source card ejected outline toX103.725 atnominalplacement')
 x,y=pos('J406');rect('TOUCH_FFC_EXIT','J406',[x+3.05,y-3.5,111,y+3.5],'7mm wide flat-flex insertion/exit allowance to right')
 rect('TOUCH_LOCK_TOP_ACCESS','J406',[x-1.2,y-3.5,x+4.8,y+3.5],'Top approach to flip/slide lock; no adjacent tall fitted parts inside')
 x,y=pos('J601');rect('EPD_FFC_EXIT','J601',[x-9,y+5.08,x+9,111],'18mm wide flexible-cable handling allowance to bottom')
 rect('EPD_LOCK_TOP_ACCESS','J601',[x-9,y+1,x+9,99],'Top approach from bottom edge to actuator; original connector body and ownpads excluded')
 for ref in ['J102','J103']:
  x,y=pos(ref);rect(ref+'_WIRE_ENTRY',ref,[-12,y-6.5,x-3.7,y+3],'Left-going wire/ferrule insertion; 12mm outboard handling reserve')
  rect(ref+'_SCREWDRIVER_TOP',ref,[x-4.2,y-6,x+4.1,y+2.5],'Top screwdriver access over screw-terminal housing')
 x,y=pos('J801');rect('SPEAKER_WIRE_ENTRY','J801',[x+3.7,y-3,111,y+7],'Right-going speaker wire insertion; pairedBTL path later mustkeepawayfromsensitive analognodes')
 rect('SPEAKER_SCREWDRIVER_TOP','J801',[x-4.2,y-2.5,x+4.2,y+6],'Top screwdriver approach to speaker terminal')
 for r in ['SW301','SW302','SW303','SW304','SW305']:
  x,y=pos(r);circle(r+'_FINGER_ACCESS',r,[x+3.25,y+2.25],5,'10mm diameter top-approach allowance; 11mm button pitch; not an enclosure ergonomic certification')
 for r in ['H1','H2','H3','H4']:circle(r+'_STANDOFF',r,pos(r),3.5,'7mm diameter standoff/screwhead allowance on both sides; verify final hardware')
 checks=[]
 for e in ev:
  s=box(*e['bounds_mm'])if e['shape']=='rect'else Point(e['center_mm']).buffer(e['radius_mm'],quad_segs=128)
  hits=[{'reference':r,'overlap_mm2':s.intersection(q).area}for r,q in g.items()if r!=e['reference']and s.intersection(q).area>1e-6]
  checks.append({'name':e['name'],'other_courtyard_intersections':hits})
 result={'status':'PASS_ENGINEERING_ACCESS_ENVELOPES'if all(not x['other_courtyard_intersections']for x in checks)else'REVIEW_INTERSECTIONS','board':str(a.board),'board_sha256':hashlib.sha256(a.board.read_bytes()).hexdigest(),'units':'mm; localboard0..99 Ydown','method':'Each envelope against every other fullF.Courtyard including offboard RFarea. Ownconnector/switch excluded. Existingall-pairPCBcourtyardDRCisseparate.','assumptions':['Cable, plug, screwdriver and finger margins are engineering design allowances, not claimed manufacturer minimums.','USBcandidate max14mm headwidth and straighttop exit; keep externalbattery/FFC/speaker/USBcables outofRF keepout.','Standoffoutside diameter<=7mm; actualfastener/head/enclosure stillneedsfitcheck.','No height-resolved3Dcollisionorflexbend-radius proof is asserted.'], 'envelopes':ev,'checks':checks}
 result['units']='mm; board-local x=0..99, y=0..99, positive y down'
 result['method']='Each operation envelope is checked against every other full front courtyard, including the off-board RF area. Its own connector or switch is excluded. All-pair PCB courtyard DRC is a separate check.'
 result['assumptions']=[
  'Cable, plug, screwdriver and finger margins are engineering design allowances, not manufacturer-certified minimums.',
  'USB plug candidate is at most 14 mm wide and exits straight through the top; route external cables outside the RF keepout.',
  'Standoff or screw-head outside diameter is at most 7 mm. Final hardware and enclosure fit still require checking.',
  'Headers accept vertically inserted 2.54 mm jumpers or individual female leads. No right-angle housing clearance is asserted.',
  'No height-resolved 3D collision, full-size fingertip clearance, or flex bend-radius proof is asserted.'
 ]
 result['expected_angles_degrees_ccw']=expected_angles
 result['reviewed_origins_mm']={r:pos(r) for r in expected_angles}
 result['vertical_header_inventory']=[{'reference':r,'value':f.GetValue(),'origin_mm':pos(r),'angle_degrees_ccw':f.GetOrientationDegrees()%360,'courtyard_bounds_mm':list(g[r].bounds),'operation':'vertical insertion; lateral cable sweep not reserved'}for r,f in fps.items()if 'WR_PHD_' in str(f.GetFPID().GetLibItemName())]
 a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(result['status']);print(json.dumps([c for c in checks if c['other_courtyard_intersections']],indent=2))
if __name__=='__main__':main()
