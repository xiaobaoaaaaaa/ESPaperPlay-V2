#!/usr/bin/env python3
"""Generate the initial editable KiCad power draft, using Python's standard library.

Writes to --output only. Do not regenerate over subsequent manual KiCad edits.
Geometry is in 1.27 mm grid units; electrical connections are checked from KiCad's
exported netlist separately, rather than trusting these drawing declarations.
"""
from pathlib import Path
import argparse
import json
import math
import re
import uuid

PROJECT = 'ESPaperPlay_Devboard'
GRID = 1.27
NS = uuid.UUID('a9488e55-063b-420c-baa4-9aa1ae07397e')
LIBDIR = Path('/usr/share/kicad/symbols')
LIBS = {}
CUSTOM = {}
GLOBAL = {'GND', 'VBUS_5V', 'BAT_PROT', 'SYS_RAW', 'SYS', '3V3_AON',
          'USB_EN1', 'USB_EN2', 'CHARGE_ALLOW', 'PGOOD_N', 'CHG_N', 'VBUS_SENSE_N'}

def uid(key): return str(uuid.uuid5(NS, key))
def q(s): return json.dumps(str(s), ensure_ascii=False)
def n(x): return f'{x:.4f}'.rstrip('0').rstrip('.') if x else '0'
def mm(g): return round(g * GRID, 4)

def block(s, start):
    depth = 0; string = False; escape = False
    for i in range(start, len(s)):
        c = s[i]
        if string:
            if escape: escape = False
            elif c == '\\': escape = True
            elif c == '"': string = False
        elif c == '"': string = True
        elif c == '(': depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0: return s[start:i + 1]
    raise ValueError('Unclosed S-expression')

def children(raw):
    pos = raw.index('(') + 1
    while pos < len(raw):
        if raw[pos] == '(':
            b = block(raw, pos); yield b; pos += len(b)
        else: pos += 1

def standard(libid):
    if libid in LIBS: return LIBS[libid]
    library, name = libid.split(':')
    rawfile = (LIBDIR / f'{library}.kicad_sym').read_text()
    raw = block(rawfile, rawfile.index('(symbol ' + q(name) + '\n'))
    parent = re.search(r'\(extends "([^"]+)"\)', raw)
    if parent:
        pname = parent[1]
        inherited = standard(library + ':' + pname)
        overrides = {re.match(r'\(property "([^"]+)"', x)[1]: x
                     for x in children(raw) if x.startswith('(property ')}
        parts = []
        for x in children(inherited):
            if x.startswith('(property '):
                key = re.match(r'\(property "([^"]+)"', x)[1]
                x = overrides.pop(key, x)
            if x.startswith('(symbol '):
                x = x.replace('(symbol "' + pname + '_', '(symbol "' + name + '_', 1)
            parts.append(x)
        parts.extend(overrides.values())
        raw = '(symbol ' + q(libid) + '\n' + '\n'.join(parts) + ')'
    else:
        raw = raw.replace('(symbol ' + q(name), '(symbol ' + q(libid), 1)
    LIBS[libid] = raw
    return raw

def prop(name, value, x, y, hide=False, size=1.05, justify='', angle=0):
    return (f'(property {q(name)} {q(value)} (at {n(x)} {n(y)} {angle}) '
            f'(effects (font (size {size} {size})) '
            + (f'(justify {justify}) ' if justify else '')
            + ('(hide yes)' if hide else '') + '))')

def custom(name, pin_defs, width, height, footprint, datasheet):
    # pin_defs: number, name, electrical type, x, y, angle, in grid units.
    raw = f'''(symbol {q('ESPaperPlay:' + name)}
      (pin_names (offset 0.508)) (exclude_from_sim no) (in_bom yes) (on_board yes)
      {prop('Reference', 'U', 0, mm(height + 2))}
      {prop('Value', name, 0, mm(-height - 2))}
      {prop('Footprint', footprint, 0, 0, True)}
      {prop('Datasheet', datasheet, 0, 0, True)}
      (symbol {q(name + '_0_1')}
        (rectangle (start {mm(-width)} {mm(height)}) (end {mm(width)} {mm(-height)})
          (stroke (width 0.254) (type default)) (fill (type background))))
      (symbol {q(name + '_1_1')}'''
    for number, pname, kind, x, y, angle in pin_defs:
        raw += f'''(pin {kind} line (at {mm(x)} {mm(y)} {angle}) (length 2.54)
          (name {q(pname)} (effects (font (size 1.05 1.05))))
          (number {q(number)} (effects (font (size 1.05 1.05)))))'''
    raw += '))'
    CUSTOM['ESPaperPlay:' + name] = raw
    LIBS['ESPaperPlay:' + name] = raw

def pininfo(libid):
    raw = LIBS[libid] if libid in LIBS else standard(libid)
    result = []
    for m in re.finditer(r'\(pin (?:input|output|bidirectional|tri_state|passive|free|unspecified|power_in|power_out|open_collector|open_emitter|no_connect) ', raw):
        b = block(raw, m.start())
        a = re.search(r'\(at ([\d.-]+) ([\d.-]+) ([\d.-]+)\)', b)
        num = re.search(r'\(number "([^"]+)"', b)[1]
        result.append((num, float(a[1]), float(a[2]), float(a[3])))
    return result

class Sheet:
    def __init__(self, key, title, page, root=False):
        self.key = key; self.title = title; self.page = page; self.root = root
        self.uuid = uid(key); self.sheet_uuid = uid('sheet/' + key)
        self.path = '/' + uid('root') + ('' if root else '/' + self.sheet_uuid)
        self.parts = []; self.ids = set(); self.components = {}; self.counter = 0
    def unique(self, kind):
        self.counter += 1; return uid(f'{self.key}/{kind}/{self.counter}')
    def wire_mm(self, a, b):
        if a == b: return
        self.parts.append(f'(wire (pts (xy {n(a[0])} {n(a[1])}) (xy {n(b[0])} {n(b[1])})) '
                          f'(stroke (width 0) (type default)) (uuid {q(self.unique("wire"))}))')
    def label_mm(self, net, p, side='right'):
        # Global labels point toward their anchor; local labels sit above wire.
        glob = net in GLOBAL
        angle = 0 if side == 'left' else 180
        if glob:
            self.parts.append(f'''(global_label {q(net)} (shape bidirectional)
              (at {n(p[0])} {n(p[1])} {angle})
              (effects (font (size 1.05 1.05)) (justify {"left" if angle == 0 else "right"}))
              (uuid {q(self.unique('glabel'))})
              {prop('Intersheetrefs', '${INTERSHEET_REFS}', *p, True)})''')
        else:
            self.parts.append(f'''(label {q(net)} (at {n(p[0])} {n(p[1])} 0)
              (effects (font (size 1.05 1.05)) (justify {side} bottom))
              (uuid {q(self.unique('label'))}))''')
    def text(self, text, x, y, size=1.3):
        self.parts.append(f'''(text {q(text)} (at {mm(x)} {mm(y)} 0)
          (effects (font (size {size} {size})) (justify left top))
          (uuid {q(self.unique('text'))}))''')
    def section(self, title, x, y): self.text(title, x, y, 1.8)
    def comp(self, libid, ref, value, x, y, angle=0, dnp=False, footprint=None, note='', prop_pos=None):
        raw = LIBS.get(libid) or standard(libid); self.ids.add(libid)
        x = mm(x); y = mm(y)
        pins = pininfo(libid); a = math.radians(angle)
        actual = {num: (round(x + dx*math.cos(a) - dy*math.sin(a), 4),
                        round(y - dx*math.sin(a) - dy*math.cos(a), 4), (pa + angle) % 360)
                  for num, dx, dy, pa in pins}
        def libprop(key):
            m = re.search(r'\(property ' + q(key) + r' "([^"]*)"', raw)
            return m[1] if m else ''
        if footprint is None: footprint = libprop('Footprint')
        if prop_pos:
            rx, ry, vx, vy = [mm(v) for v in prop_pos]
        elif ref.startswith('U'):
            top = min(p[1] for p in actual.values())
            rx, ry, vx, vy = x-16.51, top-6.35, x-16.51, top-3.81
        elif angle == 90:
            rx, ry, vx, vy = x, y-5.08, x, y-2.54
        else:
            offset = 6.35 if ref.startswith('Q') else 3.81
            rx, ry, vx, vy = x+offset, y-1.27, x+offset, y+1.27
        hidden = ref.startswith('#')
        refs = ''.join(f'(pin {q(p[0])} (uuid {q(uid(ref + "/pin/" + p[0]))}))' for p in pins)
        self.parts.append(f'''(symbol (lib_id {q(libid)}) (at {n(x)} {n(y)} {angle}) (unit 1)
          (exclude_from_sim no) (in_bom {"no" if hidden else "yes"}) (on_board {"no" if hidden else "yes"})
          (dnp {"yes" if dnp else "no"}) (uuid {q(uid(ref))})
          {prop('Reference', ref, rx, ry, hidden, justify='' if angle == 90 or ref.startswith('U') else 'left', angle=angle)}
          {prop('Value', value, vx, vy, hidden, justify='' if angle == 90 or ref.startswith('U') else 'left', angle=angle)}
          {prop('Footprint', footprint, x, y, True)}
          {prop('Datasheet', libprop('Datasheet'), x, y, True)}
          {prop('Design_Note', note, x, y, True)}
          {refs} (instances (project {q(PROJECT)} (path {q(self.path)} (reference {q(ref)}) (unit 1)))))''')
        self.components[ref] = actual
        return ref
    def net(self, ref, pin, net, length=5, side=None):
        x, y, angle = self.components[ref][str(pin)]
        if net is False: return  # Routed explicitly below, checked in exported netlist.
        if net is None:
            self.parts.append(f'(no_connect (at {n(x)} {n(y)}) (uuid {q(self.unique("nc"))}))'); return
        a = math.radians(angle)
        end = (round(x - mm(length)*math.cos(a), 4), round(y + mm(length)*math.sin(a), 4))
        self.wire_mm((x, y), end)
        self.label_mm(net, end, side or ('right' if math.cos(a) > .5 else 'left'))
    def connect(self, ref, mapping):
        seen = {}
        for pin, net in mapping.items():
            pos = self.components[ref][str(pin)][:2]
            if pos in seen:
                assert seen[pos] == net, (ref, pin)
                continue
            seen[pos] = net; self.net(ref, pin, net)
        assert set(map(str, mapping)) == set(self.components[ref]), (ref, mapping, self.components[ref])
    def passive(self, kind, ref, value, x, y, net1, net2, angle=0, dnp=False, footprint='', note=''):
        self.comp('Device:' + kind, ref, value, x, y, angle, dnp, footprint, note)
        self.connect(ref, {'1': net1, '2': net2})
    def flag(self, net, x, y, index):
        r = self.comp('power:PWR_FLAG', f'#FLG{index}', 'PWR_FLAG', x, y)
        self.net(r, '1', net, 0)
    def join_pins(self, ref, pins, net, direction, length=5):
        points=[self.components[ref][str(p)][:2] for p in pins]
        line_y=points[0][1]+direction*mm(length)
        for x,y in points: self.wire_mm((x,y),(x,line_y))
        self.wire_mm((min(p[0] for p in points),line_y),(max(p[0] for p in points),line_y))
        mid=(round(sum(p[0] for p in points)/len(points),4),line_y)
        # Put a junction where the labelled vertical branch meets the common rail.
        self.parts.append(f'(junction (at {n(mid[0])} {n(mid[1])}) (diameter 0) '
                          f'(color 0 0 0 0) (uuid {q(self.unique("junction"))}))')
        end=(mid[0],round(line_y+direction*mm(3),4))
        self.wire_mm(mid,end); self.label_mm(net,end,'left')
    def connector(self, ref, value, x, y, nets):
        lib = f'Connector_Generic:Conn_01x{len(nets):02d}'
        self.comp(lib, ref, value, x, y, footprint='', note='Functional test interface; physical connector/rating TBD')
        self.connect(ref, {str(i+1): v for i, v in enumerate(nets)})
    def save(self, out):
        root_instances = '(sheet_instances (path "/" (page "1")))' if self.root else ''
        txt = f'''(kicad_sch (version 20250114) (generator "eeschema") (generator_version "10.0")
          (uuid {q(self.uuid)}) (paper "A3")
          (title_block (title {q(self.title)}) (date "2026-11-01") (rev "r0 DRAFT")
            (company "ESPaperPlay / xiaobaoaaaaaa")
            (comment 1 "DESIGN REVIEW ONLY - NO PCB RELEASE / NO BATTERY CHARGE APPROVAL"))
          (lib_symbols {''.join(LIBS[i] for i in sorted(self.ids))})
          {''.join(self.parts)} {root_instances} (embedded_fonts no))'''
        (out / f'{self.key if not self.root else PROJECT}.kicad_sch').write_text(txt + '\n')

def make_custom_symbols():
    custom('TPS63802DLA', [
        ('10','VIN','power_in',-10,6,0),('1','EN','input',-10,2,0),
        ('2','MODE','input',-10,-2,0),('3','AGND','power_in',-2,-10,90),
        ('8','PGND','power_in',2,-10,90),('4','FB','input',10,-2,180),
        ('5','PG','open_collector',10,-6,180),('6','VOUT','power_out',10,6,180),
        ('9','L1','passive',-2,10,270),('7','L2','passive',2,10,270)], 8,8,'',
        'https://www.ti.com/lit/ds/symlink/tps63802.pdf')
    iox = [('24','VCC','power_in',0,20,270),('12','GND','power_in',0,-20,90),
           ('1','~{INT}','open_collector',-12,-8,0),('2','A1','input',-12,-12,0),
           ('21','A0','input',-12,-14,0),('3','~{RESET}','input',-12,6,0),
           ('22','SCL','input',-12,12,0),('23','SDA','bidirectional',-12,14,0)]
    for i, pin in enumerate([4,5,6,7,8,9,10,11,13,14,15,16,17,18,19,20]):
        pname = f'P0{i}' if i < 8 else f'P1{i-8}'
        iox.append((str(pin),pname,'bidirectional',12,16-i*2,180))
    custom('TCA9539PW',iox,10,18,'Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm',
           'https://www.ti.com/lit/ds/symlink/tca9539.pdf')
    custom('MAX17048G+',[
        ('3','VDD','power_in',-3,10,270),('2','CELL','passive',3,10,270),
        ('7','SCL','input',-10,4,0),('8','SDA','bidirectional',-10,0,0),
        ('5','~{ALRT}','open_collector',10,4,180),('6','QSTRT','input',10,-2,180),
        ('1','CTG','input',10,-6,180),('4','GND','power_in',-2,-10,90),
        ('9','EP','power_in',2,-10,90)],8,8,
        'Package_DFN_QFN:TDFN-8-1EP_2x2mm_P0.5mm_EP0.8x1.2mm',
        'https://www.analog.com/media/en/technical-documentation/data-sheets/MAX17048-MAX17049.pdf')

def draw_charger():
    s = Sheet('POWER_INPUT_CHARGER','POWER INPUT / BQ24074 CHARGER',2)
    s.section('1  POWER PATH AND PROTECTED BATTERY INTERFACE',14,14)
    s.text('5 V only. USB-C / ESD / input protection belong to the future MCU_USB sheet.',14,20)
    s.connector('J101','5V_BENCH_IN',40,44,['VBUS_5V','GND'])
    s.text('Known, current-limited source only.\nConnector / protection BOM not released.',14,56,1.1)
    s.passive('C','C101','4.7u / 16V',75,47,'VBUS_5V','GND')
    s.comp('Battery_Management:BQ24074RGT','U101','BQ24074RGT',150,65)
    s.connect('U101',{'1':'BAT_NTC','2':'BAT_PROT','3':'BAT_PROT','4':'CHG_CE_N',
        '5':'USB_EN2','6':'USB_EN1','7':'PGOOD_N','8':'GND','9':'CHG_N',
        '10':'SYS_RAW','11':'SYS_RAW','12':'CHG_ILIM','13':'VBUS_5V',
        '14':'CHG_TMR','15':None,'16':'CHG_ISET','17':'GND'})
    s.passive('C','C102','10u / 10V',195,44,'SYS_RAW','GND')
    s.passive('R','R101','0R / I_SYS',240,36,'SYS_RAW','SYS',90,
              note='Removable current measurement link; current-rated part / footprint TBD')
    s.connector('J104','SYS_TEST',293,38,['SYS','GND'])
    s.text('R101: measure total SYS load.\nCE pull-up stays on SYS_RAW side.',220,51,1.1)
    s.connector('J102','BAT_PACK_PROTECTED',40,89,['BAT_PACK_P','GND'])
    s.passive('R','R102','0R / I_BAT',77,83,'BAT_PACK_P','BAT_PROT',90,
              note='Whole protected battery current, includes gauge; current rating TBD')
    s.passive('C','C103','10u / 10V',195,84,'BAT_PROT','GND')
    s.connector('J103','PACK_NTC',40,115,['BAT_NTC','GND'])
    s.text('BAT + NTC are functional bench terminals.\nPack connector / polarity / R-T curve TBD.\nNo fixed resistor in place of pack NTC.',14,128,1.1)
    s.passive('R','R103','1.62k / 1%',237,86,'CHG_ILIM','GND',note='CALCULATED candidate: typ 0.994 A; max approx 1.073 A')
    s.passive('R','R104','3.00k / 1%',269,86,'CHG_ISET','GND',note='CALCULATED candidate: typ 297 mA, approx 263-328 mA; battery approval required')
    s.passive('R','R105','68k / 1%',300,86,'CHG_TMR','GND',note='CALCULATED candidate: typ fast timer 9.07 h; capacity / timer validation required')
    s.text('ISET / ILIM / TMR = calculation starting points, not approved charging settings.\nITERM pin 15 NC: internal termination threshold (mode dependent).',211,105,1.1)
    s.section('2  HARDWARE CHARGE INHIBIT / CURRENT MODE / STATUS',14,148)
    s.comp('Transistor_FET:AO3400A','Q101','AO3400A',69,178)
    s.connect('Q101',{'1':'CHG_GATE','2':'GND','3':'CHG_CE_N'})
    s.passive('R','R106','47k / 1%',97,169,'SYS_RAW','CHG_CE_N')
    s.passive('R','R107','100k',43,191,'CHG_GATE','GND')
    s.passive('R','R108','0R CHG_ARM',40,169,'CHARGE_ALLOW','CHG_GATE',90,True,
              note='DEFAULT DNP: hardware inhibit until battery / NTC approved')
    s.connector('J105','RECOVERY_CE',114,195,['CHG_CE_N','GND'])
    s.text('J105 normally OPEN. Recovery only: MAIN_RUN OFF, AMP disabled,\nEN1/EN2=00, qualified pack + NTC, known bench source.\nR108 is DNP: firmware cannot enable charging in initial assembly.',14,211,1.05)
    s.passive('R','R109','100k',151,177,'USB_EN1','GND')
    s.passive('R','R110','100k',180,177,'USB_EN2','GND')
    s.passive('R','R111','100k',221,177,'3V3_AON','PGOOD_N')
    s.passive('R','R112','100k',251,177,'3V3_AON','CHG_N')
    s.text('EN2 EN1: 00=100mA, 01=500mA,\n10=RILIM, 11=USB suspend.\nDo not infer source capacity from VBUS.',143,197,1.05)
    s.flag('VBUS_5V',106,124,'101'); s.flag('GND',139,124,'102')
    s.flag('SYS',171,124,'201'); s.flag('3V3_AON',205,124,'202')
    s.text('PWR_FLAG: normal RUN with R101/R203 populated.\nERC does not model removable links or input protection.',93,131,1.0)
    s.section('3  AON-SAFE VBUS SENSE',224,119)
    s.comp('Transistor_FET:AO3400A','Q201','AO3400A',280,139)
    s.connect('Q201',{'1':'VBUS_GATE','2':'GND','3':'VBUS_SENSE_N'})
    s.passive('R','R220','100k',306,139,'3V3_AON','VBUS_SENSE_N')
    s.passive('R','R221','10k',245,135,'VBUS_5V','VBUS_GATE',90)
    s.passive('R','R222','47k',245,158,'VBUS_GATE','GND',
              note='With R221=10k and C101=4.7u, passive VBUS discharge tau approx 0.27s; unplug delay to measure')
    s.text('LOW = VBUS present. AON-off isolation.\nPGOOD still required for valid input.',265,158,1.0)
    return s

def draw_control():
    s = Sheet('POWER_3V3_CONTROL','3.3 V REGULATOR / POWER CONTROL / GAUGE',3)
    s.section('1  MAIN BUCK-BOOST / MEASUREMENT / RECOVERY',14,14)
    s.comp('ESPaperPlay:TPS63802DLA','U201','TPS63802DLA',74,56)
    s.connect('U201',{'1':'MAIN_EN','2':'REG_MODE','3':False,'4':'REG_FB',
        '5':'REG_PG','6':'3V3_REG','7':False,'8':False,'9':False,'10':'SYS'})
    s.join_pins('U201',['3','8'],'GND',1,3)
    s.comp('Device:L','L201','0.47uH',74,28,90,footprint='',
           note='Effective L 0.37-0.57uH; saturation/current/DC resistance TBD')
    for upin,lpin,net in [('9','1','SW_L1'),('7','2','SW_L2')]:
        a=s.components['U201'][upin][:2]; b=s.components['L201'][lpin][:2]
        corner=(b[0],a[1]-mm(5))
        s.wire_mm(a,(a[0],corner[1])); s.wire_mm((a[0],corner[1]),corner); s.wire_mm(corner,b)
        s.label_mm(net,corner,'right' if upin=='9' else 'left')
    s.passive('C','C201','10u / 10V',23,49,'SYS','GND')
    s.passive('C','C202','22u / 10V',122,43,'3V3_REG','GND')
    s.passive('R','R201','511k / 1%',157,40,'3V3_REG','REG_FB')
    s.passive('R','R202','91k / 1%',157,67,'REG_FB','GND')
    s.passive('R','R203','0R / I_3V3',203,32,'3V3_REG','3V3_AON',90,
              note='Measurement link downstream of COUT and feedback; current-rated part TBD')
    s.connector('J201','3V3_AON_TEST',219,65,['3V3_AON','GND'])
    s.text('Never parallel an external 3.3 V source.\nOpen R203 before external injection.\nC202 + R201 remain upstream of R203.',187,47,1.05)
    s.passive('R','R204','100k',26,90,'SYS','MAIN_EN_PULL')
    s.connector('J202','MAIN_RUN_SELECT',62,88,['MAIN_EN_PULL','MAIN_EN','GND'])
    s.passive('R','R205','1M',93,90,'MAIN_EN','GND')
    s.text('J202: 1-2 RUN; 2-3 OFF / recovery.\nOne shunt only. Open defaults OFF.',14,108,1.05)
    s.passive('R','R206','100k',124,90,'REG_MODE','GND')
    s.connector('J203','PWM_TEST_OPEN',160,91,['REG_MODE','3V3_REG'])
    s.passive('R','R207','100k',202,88,'3V3_REG','REG_PG')
    s.connector('J204','REG_PG_TEST',236,88,['REG_PG','GND'])
    s.text('MODE low = automatic PFM/PWM.\nU201 exact DLA footprint not assigned.\nPG is a test signal, not a new MCU GPIO.',187,104,1.05)
    s.section('2  AON I2C CONTROL / RESET DEFAULTS',14,126)
    s.comp('ESPaperPlay:TCA9539PW','U202','TCA9539PW / 0x74',80,167)
    ports={'24':'3V3_AON','12':'GND','1':'IOX_INT_N','2':'GND','21':'GND',
        '3':'IOX_RESET_N','22':'I2C_AON_SCL','23':'I2C_AON_SDA','4':'EPD_EN','5':'SD_EN',
        '6':'TOUCH_EN','7':'PGOOD_N','8':'CHG_N','9':'SD_CD_N','10':'USB_EN1','11':'CHARGE_ALLOW',
        '13':'TOUCH_IO_EN','14':'USB_EN2','15':'FUEL_ALERT_N',
        '16':'IOX_SP13','17':'IOX_SP14','18':'IOX_SP15','19':'IOX_SP16','20':'IOX_SP17'}
    s.connect('U202',ports)
    s.text('P13-P17 pulled LOW: keep INPUT.\nRESET: inputs / output latch=1.\nWrite safe latch BEFORE direction.',57,197,1.05)
    s.passive('C','C203','100n',23,148,'3V3_AON','GND')
    s.passive('R','R208','10k',23,174,'IOX_RESET_N','GND')
    s.passive('R','R209','100k',23,200,'3V3_AON','IOX_INT_N')
    s.passive('R','R210','4.7k',139,144,'3V3_AON','I2C_AON_SDA')
    s.passive('R','R211','4.7k',168,144,'3V3_AON','I2C_AON_SCL')
    s.passive('R','R212','100k',139,173,'EPD_EN','GND')
    s.passive('R','R213','100k',168,173,'SD_EN','GND')
    s.passive('R','R214','100k',139,201,'TOUCH_EN','GND')
    s.passive('R','R215','100k',168,201,'TOUCH_IO_EN','GND')
    s.connector('J205','MCU_BRINGUP',211,148,['3V3_AON','GND','I2C_AON_SDA','I2C_AON_SCL','IOX_RESET_N','VBUS_SENSE_N'])
    s.text('J205: GPIO10 / 13 / 42 / 2.\nDo not back-power AON from a core board.',187,166,1.0)
    s.connector('J206','DOMAINS_CONTROL',211,181,['EPD_EN','SD_EN','TOUCH_EN','TOUCH_IO_EN','SD_CD_N','GND'])
    s.passive('R','R216','100k',243,182,'3V3_AON','SD_CD_N')
    s.text('Load switches, TMUX1511, EPD/SD/audio and MCU are future sheets.\nStart I2C at 100kHz; edge timing / gauge power-off leakage to verify.',14,218,1.0)
    # Third vertical strip: battery-powered gauge and reserved GPIO pulls.
    s.section('3  BATTERY GAUGE',258,14)
    s.comp('ESPaperPlay:MAX17048G+','U203','MAX17048G+ / 0x36',282,61,
           prop_pos=(270,31,270,33))
    s.connect('U203',{'1':'GND','2':False,'3':False,'4':False,'5':'FUEL_ALERT_N',
        '6':'GND','7':'GAUGE_SCL','8':'GAUGE_SDA','9':False})
    s.join_pins('U203',['2','3'],'BAT_PROT',-1,6)
    s.join_pins('U203',['4','9'],'GND',1,3)
    s.passive('C','C204','100n',307,36,'BAT_PROT','GND')
    s.passive('R','R217','0R',263,103,'I2C_AON_SCL','GAUGE_SCL',
              note='Isolation debug link; gauge Ioff when BAT absent is unverified')
    s.passive('R','R218','0R',298,103,'I2C_AON_SDA','GAUGE_SDA',
              note='Isolation debug link; does not itself guarantee Ioff')
    s.passive('R','R219','100k',307,80,'3V3_AON','FUEL_ALERT_N')
    s.section('4  SPARE PORT DEFAULTS',258,128)
    for idx,(x,y) in enumerate([(262,152),(285,152),(308,152),(262,182),(285,182)]):
        s.passive('R',f'R{223+idx}','100k',x,y,f'IOX_SP{13+idx}','GND')
    s.text('P13-P17 reserved.\nRemove pulls only with\na reviewed new assignment.',300,181,1.0)
    return s

def draw_root(charger, control):
    s = Sheet('root','ESPaperPlay DEVELOPMENT BOARD - POWER DRAFT',1,True)
    s.section('ESPaperPlay  /  DEVELOPMENT BOARD r0',18,20)
    s.text('Two editable power sheets. ESP32-S3-WROOM-1-N16R8 / GDEY075T7-T01.',18,30,1.5)
    s.text('DESIGN REVIEW ONLY: not a full board, not a manufacturing release.',18,39,1.5)
    for child, x in [(charger,24),(control,175)]:
        sx,sy,w,h=mm(x),mm(62),mm(125),mm(32)
        s.parts.append(f'''(sheet (at {sx} {sy}) (size {w} {h})
          (stroke (width 0.254) (type default)) (fill (color 0 0 0 0))
          (uuid {q(child.sheet_uuid)})
          {prop('Sheetname',child.key,sx,sy-2.54,justify='left')}
          {prop('Sheetfile',child.key+'.kicad_sch',sx,sy+h+2.54,justify='left')}
          (instances (project {q(PROJECT)} (path {q(s.path)} (page {q(child.page)})))))''')
    s.section('DEFINED IN THIS DRAFT',18,117)
    s.text('BQ24074 power path; protected battery / NTC interface; default charge inhibit.\nTPS63802 3.3 V regulator; measurement isolation; TCA9539 reset and control.\nMAX17048 battery gauge; AON-safe open-drain VBUS detector.\nCross-sheet global nets connect the two sheets; no hidden MCU connections.',18,126,1.5)
    s.section('ASSEMBLY AND INTEGRATION GATES',18,158)
    s.text('R108 CHG_ARM: DNP until the actual cell and NTC temperature window are approved.\nJ105 RECOVERY_CE: normally open. J202 MAIN_RUN: one shunt, 1-2 RUN / 2-3 OFF.\nUSB-C protection, MCU, domain load switches, touch isolation and audio are not drawn yet.\nBattery connector pinout, converter DLA footprint, power-link current ratings remain TBD.\nERC checks schematic rules; it does not validate charging, thermal behavior or removable links.',18,168,1.4)
    s.text('Design contract: docs/v2/hardware/power-design-spec.md\nReview instructions and exact release limits: hardware/devboard-r0/README.md',18,215,1.2)
    return s

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    make_custom_symbols()
    charger=draw_charger(); control=draw_control(); root=draw_root(charger,control)
    for sheet in (root,charger,control): sheet.save(args.output)
    definitions='\n'.join(v.replace(q(k),q(k.split(':')[1]),1) for k,v in CUSTOM.items())
    (args.output/'ESPaperPlay.kicad_sym').write_text(
        '(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor")\n'+definitions+'\n)\n')
    (args.output/'sym-lib-table').write_text('(sym_lib_table (version 7)\n'
        ' (lib (name "ESPaperPlay") (type "KiCad") (uri "${KIPRJMOD}/ESPaperPlay.kicad_sym") (options "") (descr "Locally verified power symbols")))\n')
    pro=args.output/(PROJECT+'.kicad_pro')
    if not pro.exists(): pro.write_text(json.dumps({'meta':{'filename':pro.name,'version':1}},indent=2)+'\n')
    print(f'Wrote 3 sheets / {sum(len(s.components) for s in (charger,control))} symbols to {args.output}')

if __name__=='__main__': main()
