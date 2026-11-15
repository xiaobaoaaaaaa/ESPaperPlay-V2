#!/usr/bin/env python3
from pathlib import Path
import sys,json,hashlib,argparse
import pcbnew as P
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'hardware/devboard-99').is_dir())
sys.path.insert(0,str(ROOT/'hardware/devboard-r0/tools'));from analyze_signal_paths import Analyzer
ap=argparse.ArgumentParser(description='Read-only EPD input-path centerlines, nominal barrels and debug stubs; not SI qualification.');ap.add_argument('--board',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);a=ap.parse_args();src=a.board;out=a.report;b=P.LoadBoard(str(src));an=Analyzer(b);rows={}
for label,mcu,header,buf in [('SCLK','U301.9','J301.3','U601.2'),('MOSI','U301.8','J301.4','U601.3'),('DC','U301.11','J301.6','U601.5'),('RST_N','U301.12','J301.7','U601.6')]:
 main=an.route(mcu,buf);left=an.route(mcu,header);right=an.route(header,buf);row={'main':main,'MCU_to_header':left,'header_to_buffer':right};row['debug_stub_estimate_mm']=max(0,(left['length_mm']+right['length_mm']-main['length_mm'])/2)if all(r['status']=='CONNECTED'for r in [main,left,right])else None;rows[label]=row
report={'scope':'Centerline/pad access and nominal F-B barrels only; MCU package and buffer delay/external harness excluded. No SI certification or arbitrary EPD trace-length release limit.','board_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'paths':rows};out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({n:{'main_mm':r['main'].get('length_mm'),'transitions':r['main'].get('layer_transitions'),'MCU_to_header_mm':r['MCU_to_header'].get('length_mm'),'debug_stub_mm':r['debug_stub_estimate_mm']}for n,r in rows.items()},indent=2))

raise SystemExit(any(p['status']!='CONNECTED'for row in rows.values()for p in [row['main'],row['MCU_to_header'],row['header_to_buffer']]))
