#!/usr/bin/env python3
"""Check BOM metadata, native pad IDs and preserved baseline connectivity.

This checks actual KiCad footprints using pcbnew. It does not qualify solder
processes, mechanical mating, copper current capability or analog behavior.
For r4, --delta permits only explicitly listed new pins and exact value changes.
Without --delta, the historical r2->r3 exceptions remain in effect.
"""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def netgroups(root):
    return {frozenset((n.attrib['ref'],n.attrib['pin']) for n in net.findall('node')) for net in root.findall('./nets/net')}

def check_delta_connectivity(root, previous_groups, delta):
    """Validate every added pin's named net before removing it for comparison."""
    added=delta['added_pins']
    assert isinstance(added,list),'added_pins must be a list'
    previous_pins=set().union(*previous_groups)
    allowed=set()
    nets=root.findall('./nets/net')
    for entry in added:
        assert set(entry)=={'ref','pin','net'},('invalid added pin declaration',entry)
        assert all(isinstance(entry[k],str) and entry[k] for k in entry),entry
        key=(entry['ref'],entry['pin'])
        assert key not in allowed,('duplicate added pin',key)
        assert key not in previous_pins,('declared new pin already in baseline',key)
        matches=[net for net in nets for node in net.findall('node')
                 if (node.attrib['ref'],node.attrib['pin'])==key]
        assert len(matches)==1,('added pin must appear once in netlist',key,len(matches))
        assert matches[0].attrib.get('name')==entry['net'],('added pin on wrong net',entry,matches[0].attrib.get('name'))
        allowed.add(key)
    stripped={frozenset((node.attrib['ref'],node.attrib['pin'])
                        for node in net.findall('node')
                        if (node.attrib['ref'],node.attrib['pin']) not in allowed)
              for net in nets}
    assert stripped==previous_groups,'baseline connectivity changed after removing explicitly added pins'
    return added

def main():
    p=argparse.ArgumentParser()
    p.add_argument('netlist',type=Path)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--bom',type=Path,default=Path(__file__).resolve().parents[1]/'review-r4/bom-review.json')
    p.add_argument('--delta',type=Path,help='Explicit allowed added_pins, value_changes and unassigned_footprints JSON')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    # Fedora KiCad can print PROPERTY_ENUM diagnostics on import. Parsing and
    # assertions below must still complete; diagnostics are not a GUI test.
    import pcbnew
    project=Path(__file__).resolve().parents[1]
    root=ET.parse(a.netlist).getroot()
    bom=json.loads(a.bom.read_text());rows={x['ref']:x for x in bom['items']}
    comps={x.attrib['ref']:x for x in root.findall('./components/comp')}
    delta=json.loads(a.delta.read_text()) if a.delta else None
    if delta is not None:
        assert isinstance(delta,dict) and set(delta)=={'added_pins','value_changes','unassigned_footprints'},'invalid delta schema'
        assert isinstance(delta['value_changes'],dict),'value_changes must be an object'
        assert isinstance(delta['unassigned_footprints'],list),'unassigned_footprints must be a list'
        assert all(isinstance(ref,str) for ref in delta['unassigned_footprints'])
        assert len(delta['unassigned_footprints'])==len(set(delta['unassigned_footprints'])),'duplicate unassigned reference'
    if a.baseline.suffix=='.json':
        snapshot=json.loads(a.baseline.read_text())
        previous_groups={frozenset(tuple(n) for n in group) for group in snapshot['netgroups']}
        previous_nets=snapshot['nets'];prev=snapshot['components']
    else:
        old=ET.parse(a.baseline).getroot()
        previous_groups=netgroups(old);previous_nets=len(old.findall('./nets/net'))
        prev={x.attrib['ref']:{'value':x.findtext('value'),'uuid':x.findtext('tstamps'),'dnp':x.find("property[@name='dnp']") is not None} for x in old.findall('./components/comp')}
    assert set(comps)==set(prev)==set(rows)
    if delta is not None:
        assert set(delta['value_changes'])<=set(comps),'value change references unknown component'
        assert set(delta['unassigned_footprints'])<=set(comps),'unassigned footprint references unknown component'
        added_pins=check_delta_connectivity(root,previous_groups,delta)
        assert all(entry['ref'] in comps for entry in added_pins),'added pin references unknown component'
        for ref,change in delta['value_changes'].items():
            assert isinstance(change,dict) and set(change)=={'before','after'},('invalid value change',ref)
            assert all(isinstance(change[k],str) for k in change),('value change must contain strings',ref)
            assert change['before']!=change['after'],('redundant value change',ref)
            assert prev[ref]['value']==change['before'],('value change baseline mismatch',ref)
    else:
        assert netgroups(root)==previous_groups,'electrical connectivity changed'
        added_pins=[]
    assert len(root.findall('./nets/net'))==previous_nets==178
    libs={(x.attrib['lib'],x.attrib['part']):{v.attrib['num'] for v in x.findall('./pins/pin')} for x in root.findall('./libparts/libpart')}
    cache={};checked=[];unassigned=[];dnps=[]
    for ref,c in comps.items():
        row=rows[ref];base=prev[ref]
        fp=c.findtext('footprint','');assert fp==row['footprint'],(ref,fp,row['footprint'])
        assert c.findtext('value')==row['value']
        assert c.findtext('tstamps')==base['uuid'],('UUID changed',ref)
        for key,expected in [('Manufacturer',row['manufacturer']),('Candidate_MPN',row['mpn'])]:
            assert c.findtext(f"fields/field[@name='{key}']",'')==expected,(ref,key)
        dnp=c.find("property[@name='dnp']") is not None
        assert dnp==row['dnp']==base['dnp'],(ref,'DNP changed')
        if dnp:dnps.append(ref)
        if delta is not None:
            expected=delta['value_changes'].get(ref,{}).get('after',base['value'])
            assert c.findtext('value')==expected,(ref,'value does not match explicit delta',expected)
        elif ref not in {'D601','D602','D603'}:
            assert c.findtext('value')==base['value'],(ref,'unexpected value change')
        if not fp:unassigned.append(ref);continue
        if fp not in cache:
            lib,name=fp.split(':',1)
            folder=project/'ESPaperPlay.pretty' if lib=='ESPaperPlay' else Path('/usr/share/kicad/footprints')/(lib+'.pretty')
            path=folder/(name+'.kicad_mod');assert path.is_file(),path
            native=pcbnew.FootprintLoad(str(folder),name);assert native is not None,fp
            pads=[]
            for pad in native.Pads():
                if pad.GetNumber():
                    pads.append({'number':pad.GetNumber(),'position_mm':[pcbnew.ToMM(pad.GetPosition().x),pcbnew.ToMM(pad.GetPosition().y)],'size_mm':[pcbnew.ToMM(pad.GetSize().x),pcbnew.ToMM(pad.GetSize().y)],'drill_mm':[pcbnew.ToMM(pad.GetDrillSize().x),pcbnew.ToMM(pad.GetDrillSize().y)]})
            cache[fp]={'path':str(path),'sha256':digest(path),'pads':pads,'refs':[]}
        data=cache[fp];data['refs'].append(ref)
        padset={x['number'] for x in data['pads']}
        libsource=c.find('libsource');pinset=libs[(libsource.attrib['lib'],libsource.attrib['part'])]
        assert padset==pinset,(ref,'physical pad/symbol pin mismatch',sorted(pinset-padset),sorted(padset-pinset))
        checked.append(ref)
    expected_unassigned=set(delta['unassigned_footprints']) if delta is not None else {'J102','J103','J406','J601','J801','R602','U803'}
    assert set(unassigned)==expected_unassigned,('unassigned footprint set differs',sorted(unassigned),sorted(expected_unassigned))
    assert set(dnps)=={'R108','J301','J302','J303','C501','C502'}
    inputs=[a.netlist,a.baseline,a.bom]+([a.delta] if a.delta else [])
    result={'status':'PASS','scope':'Native footprint load, numbered pad-set matching, BOM metadata, UUID/DNP preservation, explicit changes and preserved baseline netgroups after removing allowed new pins; not mechanical/assembly release.',
      'positions':len(comps),'nets':178,'baseline_connectivity_preserved':True,'explicit_added_pins':added_pins,'explicit_value_changes':delta['value_changes'] if delta is not None else {},'delta_mode':delta is not None,'dnp':sorted(dnps),'footprint_positions_checked':len(checked),'unique_footprints_checked':len(cache),'unassigned_footprints':sorted(unassigned),'footprints':cache,'inputs':{str(x):digest(x) for x in inputs}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in {'footprints','inputs'}},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
