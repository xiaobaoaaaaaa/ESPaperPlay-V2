import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { Workbook, SpreadsheetFile, FileBlob } from '@oai/artifact-tool';

const ROOT='/home/xiaobao/Projects/ESP32';
const DIR=path.join(ROOT,'build/closure-r4/workbook');
const INPUT=path.join(ROOT,'hardware/devboard-r0/review-r4/bom-review.json');
const PREVIOUS=path.join(ROOT,'hardware/devboard-r0/review-r3/bom-review.json');
const OUTPUT=path.join(ROOT,'outputs/espaperplay-bom-r4/ESPaperPlay_BOM_Review_r4.xlsx');
const raw=await fs.readFile(INPUT,'utf8');
const source=JSON.parse(raw), items=source.items;
const previous=JSON.parse(await fs.readFile(PREVIOUS,'utf8')).items;
const oldByRef=new Map(previous.map(i=>[i.ref,i]));
const changes={
  added_footprint_candidates:items.filter(i=>i.footprint&&!oldByRef.get(i.ref)?.footprint).map(i=>i.ref),
  added_mpn_candidates:items.filter(i=>i.mpn&&!oldByRef.get(i.ref)?.mpn).map(i=>i.ref),
  dnp_changes:items.filter(i=>oldByRef.has(i.ref)&&i.dnp!==oldByRef.get(i.ref).dnp).map(i=>i.ref),
};
if(items.length!==222||items.filter(i=>i.dnp).length!==6||changes.dnp_changes.length)throw new Error('r4 source position/DNP contract differs from approved review scope');
if(items.some(i=>!i.footprint)||items.filter(i=>!i.mpn).some(i=>!i.dnp))throw new Error('r4 candidate coverage is not ready');
if(JSON.stringify(items.filter(i=>!i.mpn).map(i=>i.ref).sort())!==JSON.stringify(['C501','C502']))throw new Error('unexpected intentionally blank MPNs');
const wb=Workbook.create();
const overview=wb.worksheets.add('审查总览');
const bom=wb.worksheets.add('BOM');
const fps=wb.worksheets.add('封装核对');
const FONT='Noto Sans CJK SC', ink='#1F2937', navy='#263B53', pale='#EFF3F7';
const begin=6,end=begin+items.length-1;
const cols=['位号','原理图页','数值 / 功能','数量','DNP','制造商候选','准确料号候选','KiCad 封装候选','审查状态','待闭合事项','封装状态','料号状态','','原厂资料'];
const pageNames={POWER_INPUT_CHARGER:'电源输入与充电',POWER_3V3_CONTROL:'3.3V 电源控制',MCU_CORE:'主控',POWER_DOMAINS:'电源域',USB_INPUT:'USB 输入',EPD_DISPLAY:'电子纸驱动',TOUCH_ISOLATION:'触摸隔离',STORAGE_SD:'存储卡',AUDIO:'音频'};
const tableStyle=(sheet,range,name)=>{let t=sheet.tables.add(range,true,name);t.style='TableStyleMedium2';t.showFilterButton=true;return t;};
const base=(sheet,range)=>{sheet.showGridLines=false;sheet.getRange(range).format={font:{name:FONT,size:11,color:ink},verticalAlignment:'center',rowHeight:24};};
const title=(sheet,text,last)=>{sheet.getRange('A2').values=[[text]];sheet.getRange(`A2:${last}2`).format.font={name:FONT,size:16,bold:true,color:navy};sheet.getRange(`A2:${last}2`).format.rowHeight=30;sheet.getRange(`A3:${last}3`).format.borders={bottom:{style:'thin',color:'#8FA5BB'}};};
const head=(sheet,range)=>{sheet.getRange(range).format={fill:navy,font:{name:FONT,size:11,bold:true,color:'#FFFFFF'},horizontalAlignment:'center',verticalAlignment:'center',rowHeight:30,borders:{insideVertical:{style:'thin',color:'#FFFFFF'}}};};
const width=(sheet,col,px,lastRow)=>sheet.getRange(`${col}1:${col}${lastRow}`).format.columnWidthPx=px;
const stringLines=(s,px)=>String(s??'').split('\n').reduce((n,l)=>n+Math.max(1,Math.ceil([...l].reduce((n,c)=>n+(c.charCodeAt(0)>255?14:7.5),0)/(px-16))),0);
const rowFit=(sheet,row,values,widths,min=44)=>{const lines=Math.max(...values.map((s,i)=>stringLines(s,widths[i])));sheet.getRange(`A${row}:N${row}`).format.rowHeight=Math.max(min,lines*17+10);};
base(bom,`A1:N${end}`);title(bom,'ESPaperPlay r4 候选 BOM','N');
bom.getRange('A3').values=[['一行一个位号，数量为单板位置数。料号和封装候选已补齐的项目，仍按待闭合事项执行验证。']];
bom.getRange('A4').values=[['DNP：是 = 默认不装。灰色提示 DNP，红色提示缺封装，黄色提示缺准确料号。']];
bom.getRange('A5:N5').values=[cols];
const bomRows=items.map(i=>[i.ref,pageNames[i.sheet]??i.sheet,i.value,i.quantity??1,i.dnp?'是':'否',i.manufacturer||'',i.mpn||'',i.footprint||'',i.review_state,i.required_action,i.footprint_state,i.mpn_state,'',(i.source_urls??[]).join('\n')]);
bom.getRange(`A${begin}:N${end}`).values=bomRows;
tableStyle(bom,`A5:L${end}`,'CandidateBOM');head(bom,'A5:L5');head(bom,'N5:N5');
const bw=[80,155,205,65,65,165,260,455,150,530,125,120,22,570];
bw.forEach((w,i)=>width(bom,String.fromCharCode(65+i),w,end));
bom.getRange(`A${begin}:N${end}`).format.wrapText=true;
bom.getRange(`A${begin}:N${end}`).format.verticalAlignment='top';
bom.getRange(`A${begin}:L${end}`).format.fill='#FFFFFF';
for(let r=begin;r<=end;r+=2)bom.getRange(`A${r}:L${r}`).format.fill='#F2F5F8';
bom.getRange(`D${begin}:D${end}`).setNumberFormat('0');
bom.getRange(`D${begin}:E${end}`).format.horizontalAlignment='center';
bomRows.forEach((r,i)=>rowFit(bom,begin+i,r,bw));
bom.getRange(`E${begin}:E${end}`).dataValidation={rule:{type:'list',values:['是','否']}};
bom.getRange(`A${begin}:L${end}`).conditionalFormats.addCustom(`=$E${begin}="是"`,{fill:'#E5E7EB',font:{color:'#596477'}});
bom.getRange(`H${begin}:H${end}`).conditionalFormats.addCustom(`=$H${begin}=""`,{fill:'#FDE8E7',font:{color:'#9B2525',bold:true}});
bom.getRange(`G${begin}:G${end}`).conditionalFormats.addCustom(`=$G${begin}=""`,{fill:'#FFF1C2',font:{color:'#8A5A00'}});
bom.freezePanes.freezeRows(5);bom.freezePanes.freezeColumns(1);
bom.tabColor='#7E93AB';

base(overview,'A1:C35');title(overview,'ESPaperPlay 开发板 r4 BOM 审查','C');
width(overview,'A',330,35);width(overview,'B',155,35);width(overview,'C',740,35);
overview.getRange('A3').values=[[`审查日期：${source.date}`]];
overview.getRange('A4').values=[['型号 / 封装候选齐全不代表量产批准。实际电池充电仍禁止，关键电容有效值仍待证明。']];
overview.getRange('A4:C4').format.font={name:FONT,size:11,color:'#9B2525',bold:true};
overview.getRange('A6:C6').values=[['统计项','位号数','口径']];head(overview,'A6:C6');
const metrics=[
 ['全部位置',`=COUNTA('BOM'!$A$${begin}:$A$${end})`,'包含所有默认装配与 DNP 位置'],
 ['DNP 位置',`=COUNTIFS('BOM'!$E$${begin}:$E$${end},"是")`,'DNP 始终独立保留，选定封装不代表改为装配'],
 ['默认装配候选',`=COUNTIFS('BOM'!$E$${begin}:$E$${end},"否")`,'仅表示原理图默认装配状态'],
 ['有封装候选','=B7-B11','已指定候选不等于通过钢网、焊接或机械装配验收'],
 ['未指定封装',`=COUNTBLANK('BOM'!$H$${begin}:$H$${end})`,'候选覆盖统计，不包含实际线束、转接链和贴装资格'],
 ['有准确料号候选','=B7-B13','含 DNP 候选，不能据此直接下单'],
 ['未指定准确料号',`=COUNTBLANK('BOM'!$G$${begin}:$G$${end})`,'USB 调谐电容 C501 / C502 默认 DNP，保留空料号'],
 ['需专项闭合',`=COUNTIFS('BOM'!$I$${begin}:$I$${end},"需专项闭合")`,'逐项待闭合事项见 BOM 表'],
 ];
overview.getRange('A7:A14').values=metrics.map(x=>[x[0]]);
overview.getRange('B7:B14').formulas=metrics.map(x=>[x[1]]);
overview.getRange('C7:C14').values=metrics.map(x=>[x[2]]);
overview.getRange('B7:B14').setNumberFormat('0');overview.getRange('B7:B14').format.font={name:FONT,size:11,bold:true,color:navy};
overview.getRange('A7:C14').format.rowHeight=31;
overview.getRange('A16:C16').values=[['资格待闭合项目','涉及位置','已确定的候选与剩余验证']];head(overview,'A16:C16');
const actions=[
 ['电池充电及安全计时','U101 / R104 / R105 / R108','已选 755570、4000mAh、1S 电池。充电电流 / 温区、NTC 曲线及保护参数尚缺。原约 297mA 与 68kΩ 安全计时组合未获资格，R108 保持 DNP，禁止充电。'],
 ['电池与音频线束','J102 / J103 / J801','3525 腔体扬声器已选 8Ω / 2W。标称 1.25mm 端子不足以确定家族和极性，开发板接口需适配线。音频初始目标 0.5W 待测，BTL 两线均不得接地。'],
 ['屏幕与触摸转接链','J601 / J406','保留既有通用 0.5mm、24P / 6P 转接延长链。候选插座原厂焊盘已建立，仍须逐线确认 pin1、接触面、端部厚度、插入深度及实际装配。'],
 ['大容量 MLCC 有效值','C101–C103 / C201–C202 等','30 个默认装配位置已补准确型号，部分改为 1206。直流偏压、温度、公差和老化后的有效容量仍待厂商数据 / 实测，标称容量不能代替有效值。'],
 ['EPD 采样与开关封装','R602 / Q601','R602 候选 WFMB2010R4700FEA（0.47Ω / 1%）及专用 2010 焊盘。电阻自身边界不代表允许 2A 流过整个 EPD 链。Q601 已按原厂 SC70 最小焊盘修正。'],
 ['麦克风声学及贴装','U803','DMM-4026-B-I2S-R 候选采用 0.60mm 非金属化 PCB 声孔。按 PUI 通用指南建立钢网 / 阻焊候选，仍须板厂工艺、密封声道和样板拾音验证。'],
 ['电源误差与热条件','R201 / R202 / F501','反馈改为 51.1k / 9.10k、0.1%、25ppm，PWM 误差预算已核。新增约 49.3µA 分压电流须纳入待机预算。PTC 候选已调整，动态、温升和故障配合仍待测。'],
 ['连接器及制造工艺','USB / SD / 按键','USB / SD 机械候选按资料补齐，仍须实际板边、插拔行程、壳体与禁布区验证。按键低电流接触、暴露焊盘钢网及过孔工艺继续审查。'],
 ];
overview.getRange('A17:C24').values=actions;overview.getRange('A17:C24').format.wrapText=true;
actions.forEach((r,i)=>overview.getRange(`A${17+i}:C${17+i}`).format.rowHeight=Math.max(58,...r.map((v,k)=>stringLines(v,[330,155,740][k])*17+10)));
overview.getRange('A26').values=[[`相对 r3 新增 ${changes.added_footprint_candidates.length} 个封装候选、${changes.added_mpn_candidates.length} 个料号候选，DNP 状态变化 ${changes.dnp_changes.length} 处。`]];
overview.getRange('A27').values=[['电池截图标称常温连续 2A、瞬时 3A 未给时长。主 3.3V / 1.5A 脉冲目标暂用台式电源验证。']];
overview.getRange('A29').values=[['数字由 BOM 明细公式统计。DNP 可筛选并驱动统计更新，资格状态仍以各位号待闭合事项为准。']];
overview.getRange('A26:C29').format.font={name:FONT,size:11,color:'#526175'};
overview.tabColor=navy;

const compressRefs=arr=>{
 const groups=new Map();for(const r of arr){const m=r.match(/^(\D+)(\d+)$/);if(!m)continue;if(!groups.has(m[1]))groups.set(m[1],[]);groups.get(m[1]).push(+m[2]);}
 let result=[];for(const [pre,nums] of groups){nums.sort((a,b)=>a-b);for(let i=0;i<nums.length;i++){let a=nums[i],b=a;while(nums[i+1]===b+1)b=nums[++i];result.push(a===b?pre+a:pre+a+'–'+pre+b);}}
 const lines=[];let line='';for(const token of result){if(line.length+token.length+1>42){lines.push(line);line=token;}else line+=(line?'、':'')+token;}if(line)lines.push(line);return lines.join('\n');
};
const fpNote=(fp,group)=>{
 if(!fp)return group.map(i=>i.ref+'：'+i.required_action).join('\n');
 if(fp.includes('WR_PHD'))return '原厂 2.54mm 节距、1.10mm 通孔。5 款封装已由 KiCad 原生载入，编号与 18 个符号实例匹配。配对线束 / 跳帽及焊接配合待确认。';
 if(fp.includes('SW_PUSH'))return '6.5×4.5mm 孔距，1.10mm 孔。两行各为一个常通接点组，按下跨组接通。普通键 47k 上拉约 70µA；EN / BOOT 约 330µA。低电流可靠性仍待实测。';
 if(fp.includes('TI_DCK'))return 'TPD2E2U06DCKR：引脚 1/2 为 IO，3 为 GND。按原厂 DCK0003A 推荐焊盘 0.95×0.40mm，跨距 2.20mm、间距 0.65mm。';
 if(fp.includes('ESP32'))return 'ESP32-S3-WROOM-1-N16R8，40 个周边焊盘及 EP41。保留库 EP41 铜面 / 过孔设计，需另核钢网、过孔工艺及天线净空。';
 if(fp.includes('USB4105'))return 'GCT USB4105-GF-A：16 个逻辑触点映射至 12 个物理 SMT 焊区，4 个接地外壳孔、2 个定位孔。板厚、板边与插脚工艺待验证。';
 if(fp.includes('DM3AT'))return 'Hirose DM3AT-SF-PEJM5 推推式。触点、检测端、壳体与机械图已按 r4 审查记录核对。实际板边、退卡行程及全层禁布区仍须布局和样板验证。';
 if(fp.includes('TMUX')||fp.includes('TSSOP-14'))return 'TMUX1511PWR，TSSOP-14，0.65mm 间距。编号已核对。现用 IPC 焊盘与 TI 示例存在小差异，作为工艺候选保留。';
 if(fp.includes('Capacitor'))return '默认装配位置已有准确候选，USB 调谐 C501 / C502 保持 DNP 空料号。尺寸与型号已核不代表偏压下有效容量合格；逐项验证温度、公差、老化和电气包络。';
 if(fp.includes('Resistor_SMD'))return '普通阻值候选采用 Vishay CRCW，0603 普通电阻 1% / 100ppm。R201 / R202 使用 TNPW 0.1% / 25ppm。零欧通流、温升及扬声器跳线仍按实际负载验证。';
 if(fp.includes('HYCW3D'))return 'HYCW3D-05FPC24-200B：24 个触点与 2 个 SH 固定焊盘。沿用原工程编号习惯；通用转接链的针序、接触面、端部厚度和插入尺寸必须实物确认。';
 if(fp.includes('LAIL-FPC'))return 'LAIL-FPC-CDX01-6P0.5-GW：6 个触点与 2 个 SH 固定焊盘。闭合高度 1.00±0.10mm。双面接触不保证延长链针序，样品配合及锁扣空间待核。';
 if(fp.includes('PUI_DMM'))return '0.60mm NPTH 声孔候选，依据 PUI 同型号适用的通用指南，孔径不小于 0.50mm 且不镀铜。1:1 铜焊盘、85% 钢网开口为候选，环形声学密封和实际拾音待测。';
 if(fp.includes('Vishay_SC70'))return 'Si1308EDL-T1-GE3，1G / 2S / 3D。按 Vishay AN826 专用 SC70 推荐最小焊盘建立 0.648×0.559mm 候选，替换原 0.45mm 宽通用焊盘。';
 if(fp.includes('Vishay_WFM'))return 'WFMB2010R4700FEA：0.47Ω / 1%，2010 焊盘 1.25×3.00mm。2W 额定对应端子 110℃。仅电阻拟定 Irms≤1A、Ipeak≤2A 的验证包络，实际 EPD 电流和温度仍待测。';
 if(fp.includes('CRF0805'))return '电源零欧采用 Bourns CRF0805 专用跳线候选，依据原厂几何建立本地封装。电流、温升与走线条件仍需实测。';
 if(fp.includes('MAX98357'))return 'MAX98357A 的 T1633-4 3×3mm 封装候选，中心焊盘按资料核对。EP 钢网、散热与功率 / 实际扬声器负载待验证。';
 if(fp.includes('RGT0016'))return 'BQ24074RGT 对应 RGT0016C。暴露焊盘、焊盘编号已按原厂图核对；钢网、热设计、NTC 与电池充电边界待验证。';
 if(fp.includes('DLA0010'))return 'TPS63802DLAR 对应 DLA0010A VSON-HR，含非对称功率焊盘。依原厂焊盘图建本地候选，短电流环路与热 / 钢网仍待布局审查。';
 return '按准确订货号与资料建立候选。需结合本表位号与 BOM 中待闭合事项确认焊接、负载及实际装配条件，不能直接视为生产放行。';
};
const groups=new Map();for(const i of items){let k=i.footprint||'';if(!groups.has(k))groups.set(k,[]);groups.get(k).push(i);}
const ordered=[...groups].sort((a,b)=>!a[0]?-1:!b[0]?1:a[0].localeCompare(b[0]));
const fEnd=5+ordered.length;
base(fps,`A1:F${fEnd}`);title(fps,'封装候选分组核对','F');
fps.getRange('A3').values=[['按 KiCad 封装候选分组，位号数量读取 BOM。候选几何核对与实物 / 制造资格分别审查。']];
fps.getRange('A5:F5').values=[['KiCad 封装候选','位号数','对应位号','器件候选示例','资料核对与待闭合要点','']];
const fr=ordered.map(([f,g])=>[f||'未指定',null,compressRefs(g.map(i=>i.ref)),[...new Set(g.map(i=>i.mpn).filter(Boolean))].slice(0,3).join('\n'),fpNote(f,g),'']);
fps.getRange(`A6:F${fEnd}`).values=fr;
for(let k=0;k<ordered.length;k++){const row=k+6;fps.getRange(`B${row}`).formulas=[[ordered[k][0]?`=COUNTIFS('BOM'!$H$${begin}:$H$${end},A${row})`:`=COUNTBLANK('BOM'!$H$${begin}:$H$${end})`]];}
tableStyle(fps,`A5:E${fEnd}`,'FootprintReview');head(fps,'A5:E5');
const fw=[470,75,410,260,760,20];fw.forEach((w,i)=>width(fps,String.fromCharCode(65+i),w,fEnd));
fps.getRange(`A6:E${fEnd}`).format.wrapText=true;fps.getRange(`A6:E${fEnd}`).format.verticalAlignment='top';
fps.getRange(`A6:E${fEnd}`).format.fill='#FFFFFF';
for(let r=6;r<=fEnd;r+=2)fps.getRange(`A${r}:E${r}`).format.fill='#F2F5F8';
fr.forEach((r,i)=>{const lines=Math.max(...r.slice(0,5).map((s,k)=>stringLines(s,fw[k])));fps.getRange(`A${i+6}:E${i+6}`).format.rowHeight=Math.max(76,lines*17+12);});
fps.getRange(`B6:B${fEnd}`).setNumberFormat('0');
fps.getRange(`A6:E${fEnd}`).conditionalFormats.addCustom('=$A6="未指定"',{fill:'#FDE8E7',font:{color:'#9B2525'}});
fps.freezePanes.freezeRows(5);fps.freezePanes.freezeColumns(1);fps.tabColor='#8E9DAB';

wb.recalculate();
const expected=[items.length,items.filter(i=>i.dnp).length,items.filter(i=>!i.dnp).length,items.filter(i=>i.footprint).length,items.filter(i=>!i.footprint).length,items.filter(i=>i.mpn).length,items.filter(i=>!i.mpn).length,items.filter(i=>i.review_state==='需专项闭合').length];
const assert=(x,msg)=>{if(!x)throw new Error(msg);};
let baseline=overview.getRange('B7:B14').values.flat();assert(JSON.stringify(baseline)===JSON.stringify(expected),'summary formula count mismatch '+JSON.stringify(baseline));
const changeRow=items.findIndex(i=>!i.dnp)+begin;
bom.getRange(`E${changeRow}`).values=[['是']];wb.recalculate();
const changed=overview.getRange('B8:B9').values.flat();assert(changed[0]===expected[1]+1&&changed[1]===expected[2]-1,'DNP recalculation failed');
bom.getRange(`E${changeRow}`).values=[['否']];wb.recalculate();
const restored=overview.getRange('B7:B14').values.flat();assert(JSON.stringify(restored)===JSON.stringify(expected),'restore failed');
const coverageIndex=items.findIndex(i=>i.mpn&&!i.dnp),coverageRow=coverageIndex+begin;
const qualificationBefore=bom.getRange(`I${coverageRow}:J${coverageRow}`).values;
bom.getRange(`G${coverageRow}`).values=[['']];wb.recalculate();
const missingCandidate=overview.getRange('B12:B13').values.flat();
assert(missingCandidate[0]===expected[5]-1&&missingCandidate[1]===expected[6]+1,'missing MPN coverage calculation failed');
bom.getRange(`G${coverageRow}`).values=[[items[coverageIndex].mpn]];wb.recalculate();
assert(JSON.stringify(bom.getRange(`I${coverageRow}:J${coverageRow}`).values)===JSON.stringify(qualificationBefore),'MPN completeness must not clear qualification status or action');
assert(JSON.stringify(overview.getRange('B7:B14').values.flat())===JSON.stringify(expected),'MPN restoration failed');
const errorScan=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100},summary:'formula error scan'});
const formulaError=/#REF!|#DIV\/0!|#VALUE!|#NAME\?|#N\/A|#NUM!|#NULL!|#SPILL!|#CALC!/;
assert(!formulaError.test(errorScan.ndjson??''),'formula errors found');
const keyInspection=await wb.inspect({kind:'table',range:'审查总览!A6:C14',include:'values,formulas',tableMaxRows:9,tableMaxCols:3,maxChars:5000});
await fs.writeFile(path.join(DIR,'key-inspection.ndjson'),keyInspection.ndjson+'\n');
await fs.mkdir(path.dirname(OUTPUT),{recursive:true});
await (await SpreadsheetFile.exportXlsx(wb)).save(OUTPUT);
try { await fs.rename(OUTPUT+'.inspect.ndjson',path.join(DIR,'export-inspect.ndjson')); } catch(e) { if(e.code!=='ENOENT')throw e; }
const reopened=await SpreadsheetFile.importXlsx(await FileBlob.load(OUTPUT));reopened.recalculate();
assert(JSON.stringify(reopened.worksheets.getItem('审查总览').getRange('B7:B14').values.flat())===JSON.stringify(expected),'reimport summary mismatch');
const reread=reopened.worksheets.getItem('BOM').getRange(`A6:N${end}`).values;
const normalizeBlank=rows=>rows.map(row=>row.map(v=>v==null?'':v));
assert(JSON.stringify(normalizeBlank(reread))===JSON.stringify(normalizeBlank(bomRows)),'reimport BOM values mismatch');
const groupCounts=reopened.worksheets.getItem('封装核对').getRange(`B6:B${fEnd}`).values.flat();
assert(groupCounts.reduce((a,b)=>a+b,0)===items.length,'footprint groups mismatch');
const reopenedOverview=reopened.worksheets.getItem('审查总览'),reopenedBom=reopened.worksheets.getItem('BOM');
assert(JSON.stringify(reopenedOverview.getRange('B7:B14').formulas)===JSON.stringify(metrics.map(m=>[m[1]])),'reimport lost summary formula text');
reopenedBom.getRange(`E${changeRow}`).values=[['是']];reopened.recalculate();
const reimportChanged=reopenedOverview.getRange('B8:B9').values.flat();
assert(reimportChanged[0]===expected[1]+1&&reimportChanged[1]===expected[2]-1,'reimport DNP live recalculation failed');
reopenedBom.getRange(`E${changeRow}`).values=[['否']];reopened.recalculate();
assert(JSON.stringify(reopenedOverview.getRange('B7:B14').values.flat())===JSON.stringify(expected),'reimport DNP restoration failed');
const reimportErrorScan=await reopened.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100},summary:'reimport formula error scan'});
assert(!formulaError.test(reimportErrorScan.ndjson??''),'reimport formula errors found');
const previews=[];
const targetedRefs=['U101','R104','R105','R108','R201','R602','U803','J601','J801'];
const targetedRows=Object.fromEntries(targetedRefs.map(ref=>[ref,items.findIndex(i=>i.ref===ref)+begin]));
const chargingUpdate=process.argv.includes('--charging-update');
const renderTargets=chargingUpdate
 ? [['审查总览','A1:C29','overview.png']]
 : [['审查总览','A1:C29','overview.png'],['BOM','A1:L13','bom.png'],['封装核对','A1:E10','footprints.png']];
for(const ref of chargingUpdate?['U101','R104','R105','R108']:['R602','U803','J601']){const r=targetedRows[ref];renderTargets.push(['BOM',`A${r}:L${r}`,`detail-${ref}.png`]);}
for(const [sheetName,range,file] of renderTargets){
 const blob=await reopened.render({sheetName,range,scale:1.2,format:'png'});const dest=path.join(DIR,file);await fs.writeFile(dest,new Uint8Array(await blob.arrayBuffer()));previews.push(dest);
}
const qa={date:source.date,operation_marker:{kind:'create',expected_output_count:1,format:'xlsx',successful_invocations:1},input:INPUT,input_sha256:crypto.createHash('sha256').update(raw).digest('hex'),output:OUTPUT,output_sha256:crypto.createHash('sha256').update(await fs.readFile(OUTPUT)).digest('hex'),sheets:['审查总览','BOM','封装核对'],positions:items.length,changes_from_r3:changes,metrics:{labels:metrics.map(m=>m[0]),expected,formula_values:baseline},dnp_recalculation:{row:changeRow,changed,restored:restored.slice(1,3),reimport_changed:reimportChanged,pass:true},candidate_vs_qualification_test:{ref:items[coverageIndex].ref,temporarily_blank_mpn_counts:missingCandidate,qualification_state_and_action_unchanged:true,restored:true},formula_error_scan:errorScan.ndjson,reimport_formula_error_scan:reimportErrorScan.ndjson,roundtrip:{all_bom_values_exact:true,summary_counts:true,summary_formula_text_exact:true,footprint_group_total:groupCounts.reduce((a,b)=>a+b,0)},features:{BOM_table:'A5:L'+end,freeze_rows:5,freeze_columns:1,footprint_table:'A5:E'+fEnd,dnp_validation:['是','否'],conditional_formatting:['DNP灰','缺封装红','缺料号黄']},targeted_rows:targetedRows,previews,visual_review:'pending agent inspection',limitations:['未在桌面Excel/LibreOffice实际打开；已在Artifact Tool中导出、重新读取并重算。','表中均为候选。未宣称采购库存、报价、PCB DRC或装配验证完成。']};
await fs.writeFile(path.join(DIR,'qa.json'),JSON.stringify(qa,null,2)+'\n');
console.log(JSON.stringify({output:OUTPUT,counts:baseline,groupCount:ordered.length,previews}));
