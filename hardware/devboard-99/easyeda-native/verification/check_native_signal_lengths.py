#!/usr/bin/env python3
"""Remeasure USB/SD/EPD native LINE paths; no candidate or historical geometry."""
import argparse
import json
from pathlib import Path
import native_trace_path_metrics as metrics


def self_test():
    from shapely.geometry import Point
    def contact(ident, xy, layers, kind='pad', net='N'):
        return {'id':ident,'g':Point(xy).buffer(.1),'layers':frozenset(layers),'kind':kind,'net':net}
    p=[contact('A',(0,0),[1]),contact('B',(2,0),[1])]
    rule={'id':'test','native_net':'N','from':'A','to':'B',
          'native_from':{'physical_pads':[{'id':'A'}]},'native_to':{'physical_pads':[{'id':'B'}]},
          'trunk_min_mm':0,'narrow_allowance_mm':100,'review_R20_mohm':10000}
    def line(a,b,w,ident,net='N',layer=1):
        return metrics.segment(a,b,w,ident,net,layer)
    def run(lines,pads=p,items=[],metric='length_mm'):
        return metrics.trace_path_audit(lines,pads,items,[rule],35,optimization_metric=metric)[0]
    cases=[]
    def check(name,passed,evidence):
        cases.append({'name':name,'pass':bool(passed),'evidence':evidence})
    ls=[line((0,0),(2,0),.1,'short'),line((0,0),(0,1),.8,'long1'),
        line((0,1),(2,1),.8,'long2'),line((2,1),(2,0),.8,'long3')]
    shortest=run(ls);lowest_r=run(ls,metric='trace_R20_mohm')
    check('Shortest-length optimization differs from lowest-resistance route',
          shortest['exposed_trace_length_mm']<lowest_r['exposed_trace_length_mm'] and
          'short'in shortest['selected_path_source_ids']and'long2'in lowest_r['selected_path_source_ids'],
          {'shortest_mm':shortest['exposed_trace_length_mm'],'resistance_route_mm':lowest_r['exposed_trace_length_mm']})
    branch=run([line((0,0),(2,0),.1,'main'),line((1,0),(1,5),.1,'leaf')])
    check('Dangling branch is not added to endpoint path',abs(branch['exposed_trace_length_mm']-1.8)<1e-8,branch['exposed_trace_length_mm'])
    disconnected=run([line((0,0),(.8,0),.1,'left'),line((1.2,0),(2,0),.1,'right')])
    check('Unconnected near-collinear gap remains open',disconnected['status']=='NO_COMPLETE_LINE_CENTERLINE_PATH',disconnected['status'])
    opposite=[contact('A',(0,0),[1]),contact('B',(2,0),[2])]
    two_layers=[line((0,0),(1,0),.1,'top'),line((1,0),(2,0),.1,'bottom',layer=2)]
    open_layers=run(two_layers,pads=opposite)
    check('Coincident layers do not join without plated access',open_layers['status']=='NO_COMPLETE_LINE_CENTERLINE_PATH',open_layers['status'])
    via=contact('V',(1,0),[1,2,15,16],kind='via')
    joined=run(two_layers,pads=opposite,items=[via])
    check('Real same-net via joins layers and is identified',joined['status']=='TRACE_ONLY_PATH_MEASURED'and joined['via_ids']==['V'],joined.get('via_ids'))
    wrong=run([line((0,0),(.8,0),.1,'left'),line((.7,0),(1.3,0),.1,'foreign','OTHER'),line((1.2,0),(2,0),.1,'right')])
    check('Wrong-net bridge cannot create a path',wrong['status']=='NO_COMPLETE_LINE_CENTERLINE_PATH',wrong['status'])
    return {'status':'PASS_SIGNAL_LENGTH_SELF_TESTS'if all(c['pass']for c in cases)else'FAIL_SIGNAL_LENGTH_SELF_TESTS','tests':cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['source', 'state', 'archive', 'output']:
        parser.add_argument('--'+key, type=Path)
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--rules', type=Path, default=Path(__file__).with_name('signal-length-rules.json'))
    args = parser.parse_args()
    if args.self_test:
        result=self_test()
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))
        return int(result['status']!='PASS_SIGNAL_LENGTH_SELF_TESTS')
    if any(getattr(args,key)is None for key in ['source','state','archive','output']):
        parser.error('--source, --state, --archive and --output are required outside --self-test')
    source, state, pads, items, lines, unparsed, evidence = metrics.load_scene(args)
    plan = json.loads(args.rules.read_text())
    byaddress = {}
    for pad in pads:
        byaddress.setdefault(pad['ref']+'.'+str(pad['pin']), []).append(pad)
    errors, rules, specifications = [], [], {}
    for item in plan['chains']+plan['branches']:
        for index, leg in enumerate(item['legs']):
            ident = item['id']+':'+str(index)
            specifications[ident] = leg
            ends = [byaddress.get(leg[key], []) for key in ['from', 'to']]
            if any(not end or any(p['net'] != leg['net'] for p in end) for end in ends):
                errors.append({'kind':'MISSING_OR_WRONG_NET_TERMINAL', 'leg':ident, 'specification':leg})
                continue
            rules.append({'id':ident, 'native_net':leg['net'], 'from':leg['from'], 'to':leg['to'],
                          'native_from':{'physical_pads':[{'id':p['id']}for p in ends[0]]},
                          'native_to':{'physical_pads':[{'id':p['id']}for p in ends[1]]},
                          'trunk_min_mm':0, 'narrow_allowance_mm':100000, 'review_R20_mohm':100000})
    selected_nets = {leg['net']for leg in specifications.values()}
    unsupported = [{'kind':kind,'id':ident,'net':body.get('netName')}for (kind, ident), body in source.items()
                   if body.get('netName')in selected_nets and kind not in {'LINE','VIA','COMPONENT','ATTR'}]
    # A selected signal FILL/ARC/etc. cannot silently disappear from a LINE-only
    # length claim. PCB logical pad objects are obtained separately from the
    # exact source/library/state comparison in load_scene.
    if unsupported:
        errors.append({'kind':'UNSUPPORTED_SELECTED_NET_COPPER_RECORDS','records':unsupported})
    measured = metrics.trace_path_audit(lines, pads, items, rules, 35, optimization_metric='length_mm')
    kept = ['path_id','net','from','to','status','exposed_trace_length_mm','selected_path_source_ids',
            'via_ids','selected_path_width_min_mm','selected_path_width_max_mm',
            'copper_overlap_contacts','direct_contact_overlaps']
    measured = [{key:row[key]for key in kept if key in row}for row in measured]
    byid = {row['path_id']:row for row in measured}
    for row in measured:
        if row['status'] != 'TRACE_ONLY_PATH_MEASURED':
            errors.append({'kind':'PATH_NOT_MEASURED','leg':row['path_id'],'status':row['status']})
    results = {}
    for category in ['chains','branches']:
        rows=[]
        for item in plan[category]:
            legs=[byid.get(item['id']+':'+str(index))for index in range(len(item['legs']))]
            complete=all(leg and leg['status']=='TRACE_ONLY_PATH_MEASURED'for leg in legs)
            rows.append({'id':item['id'],'group':item['group'],'description':item['description'],
                         'status':'MEASURED'if complete else'INCOMPLETE',
                         'exposed_trace_length_mm':sum(leg['exposed_trace_length_mm']for leg in legs)if complete else None,
                         'distinct_signal_vias':sorted({via for leg in legs if leg for via in leg.get('via_ids',[])}),
                         'component_transitions_not_measured':item.get('component_transitions',[]),
                         'legs':legs})
        results[category]=rows
    chains={row['id']:row for row in results['chains']}
    comparisons=[]
    for comparison in plan['comparisons']:
        values={name:chains[name]['exposed_trace_length_mm']for name in comparison['chains']}
        complete=all(value is not None for value in values.values())
        comparisons.append({'id':comparison['id'],'members_mm':values,
                            'maximum_difference_mm':max(values.values())-min(values.values())if complete else None,
                            'interpretation':comparison['interpretation']})
    result={'status':'ALL_SELECTED_NATIVE_SIGNAL_PATHS_MEASURED'if not errors else'SIGNAL_PATH_MEASUREMENT_FAILED',
            'inputs':{key:metrics.digest(value)for key,value in vars(args).items()if isinstance(value,Path)and key!='output'},
            'checker':metrics.digest(Path(__file__).resolve()),
            'path_helper':metrics.digest(Path(metrics.__file__).resolve()),
            'method':'Minimum exposed-length path on the current native LINE/copper-contact graph. Finite pad copper has zero length cost; via barrel and component internals are excluded. Actual positive geometry contacts join the graph; runtime POURED is never used. No historical candidate dimensions are substituted.',
            'errors':errors,'chains':results['chains'],'branches':results['branches'],'comparisons':comparisons,
            'leg_count':len(measured),'selected_net_count':len(selected_nets),
            'limitations':['Exposed trace length is not full pad-centre route length or propagation delay. It is a consistently defined geometric measurement, not a revised version of the earlier centreline-plus-pad-span candidate numbers.',
                           'Separate per-net legs stop at series resistors, buffer/mux inputs and outputs. Their physical package spans, delay, via barrels, connector mating paths and screen extension cables are not added as fictional trace lengths.',
                           'USB comparisons are board-side exposed-length skew only; uncoupled connector fanout and actual impedance/delay require separate SI/hardware validation.',
                           'Branch rows measure specified electrical terminal-to-terminal paths. They do not assert that the whole header distance is a dangling stub, or that a header lies on a main spine.',
                           'This tool verifies selected path existence and source provenance, not every copper island, shorts, return paths or final CAM. Run the dedicated topology, critical-route and adjacent-reference-plane checks.',
                           'No new pass/fail skew threshold is invented. The numerical differences remain evidence for project timing review and first-board tests.']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'chains':len(results['chains']),'branches':len(results['branches']),
                      'legs':len(measured),'errors':errors,'comparisons':comparisons},ensure_ascii=False))
    return int(bool(errors))


if __name__=='__main__':
    raise SystemExit(main())
