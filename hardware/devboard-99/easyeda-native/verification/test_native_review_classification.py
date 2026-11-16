#!/usr/bin/env python3
"""Regression tests: known geometric preferences must not hide physical faults."""
import copy,json,tempfile
from pathlib import Path
import run_final_verification as runner


def run():
    policy=json.loads((runner.HERE/'engineering-review-items.json').read_text())['EPD_PAD_SCLK_return']
    returned={'id':policy['signal_access_id'],'GND_vertical_access':policy['ground_access_id'],
              'net':policy['net'],'xy_mm':policy['xy_mm'],'distance_center_mm':policy['measured_distance_mm']}
    critical={'status':'FAIL','full_native_schematic_pin_check':{'pass':True},
              'SD_equivalent_channel_mapping':{'pass':True},'open_or_isolated_copper_nets':[],
              'missing_required_nets':[],'physical_shorts':[],'connectivity':{'N':{'pass':True}},
              'return_over_2mm':[returned]}
    local={'signal_access':policy['signal_access_id'],'ground_access':policy['ground_access_id'],
           'ground_access_verified_on_both_inner_planes':True,'distance_center_mm':policy['measured_distance_mm']}
    event={'classification':'TERMINAL_EXIT_WITHOUT_LOCAL_VERIFIED_RETURN_REVIEW','net':policy['net'],
           'own_net_plated_access_in_void':[policy['signal_access_id']],'local_GND_return_access':[local]}
    reference={'status':'GEOMETRIC_REFERENCE_REVIEW_REQUIRED','errors':[],
               'selected_nets_without_any_routed_LINE':[],'selected_nets_absent_from_native':[],
               'review_events':[event],'physical_review_events':[event],'numerical_scale_review_events':[],
               'actual_reference_corridor_checks':[{'pass':True}]}
    cases=[]
    with tempfile.TemporaryDirectory()as directory:
        p=Path(directory)/'report.json'
        def check(name,job,data,expect_hard):
            p.write_text(json.dumps(data))
            result=runner.classify_engineering_reviews([{'name':job,'report':str(p),
                'report_written_this_run':True,'returncode':1,'reported_status':data.get('status')}])
            cases.append({'name':name,'pass':bool(result['unresolved_check_failures'])==expect_hard})
        check('Exact known return remains explicitly reported preference','critical-routes',critical,False)
        d=copy.deepcopy(critical);d['open_or_isolated_copper_nets']=['SD_CD_N']
        check('Open net cannot be reclassified by known return','critical-routes',d,True)
        d=copy.deepcopy(critical);d['physical_shorts']=[{'a':'A','b':'B'}]
        check('Physical short cannot be reclassified','critical-routes',d,True)
        d=copy.deepcopy(critical);d['return_over_2mm'][0]['id']='NEW_UNKNOWN_VIA'
        check('New return location requires review','critical-routes',d,True)
        check('Actual CAM known return retains explicit review','reference-planes',reference,False)
        d=copy.deepcopy(reference);d['actual_reference_corridor_checks'][0]['pass']=False
        check('Broken GND corridor cannot be reclassified','reference-planes',d,True)
        d=copy.deepcopy(reference);d['physical_review_events'][0]['classification']='LONG_ANTIPAD_CHAIN_REVIEW'
        check('Long slot is not a return-distance preference','reference-planes',d,True)
        d=copy.deepcopy(reference);d['physical_review_events'][0]['local_GND_return_access'][0]['ground_access_verified_on_both_inner_planes']=False
        check('Unconnected return cannot be reclassified','reference-planes',d,True)
        d=copy.deepcopy(reference);n={'classification':'CAM_QUANTIZATION_SCALE_REFERENCE_GAP_REVIEW','unreferenced_centerline_length_mm':.1};d['numerical_scale_review_events']=[n];d['review_events'].append(n)
        check('Larger numerical-labeled hole remains unresolved','reference-planes',d,True)
        check('Unknown child failure stays unresolved','other-checker',{},True)
        touch=json.loads((runner.HERE/'engineering-review-items.json').read_text())['TOUCH_IO_EN_static_return']
        touch_row={'id':touch['signal_access_id'],'GND_vertical_access':touch['ground_access_id'],
                   'net':touch['net'],'xy_mm':touch['xy_mm'],
                   'distance_center_mm':touch['measured_distance_mm']}
        both=copy.deepcopy(critical);both['return_over_2mm'].append(touch_row)
        check('Exact reviewed static TOUCH enable and EPD returns remain explicit reviews','critical-routes',both,False)
        for field,value,title in [
            ('id','NEW_TOUCH_VIA','Unknown TOUCH signal ID stays unresolved'),
            ('GND_vertical_access','NEW_GROUND','Changed TOUCH ground ID stays unresolved'),
            ('net','I2S_BCLK','Static-enable review never covers a clock net'),
            ('xy_mm',[touch['xy_mm'][0]+.001,touch['xy_mm'][1]],'Changed TOUCH coordinates stay unresolved'),
            ('distance_center_mm',touch['measured_distance_mm']+.001,'Changed TOUCH distance stays unresolved'),
            ('xy_mm',None,'Malformed TOUCH coordinates cannot be accepted'),
        ]:
            d=copy.deepcopy(both);d['return_over_2mm'][-1][field]=value
            check(title,'critical-routes',d,True)
        d=copy.deepcopy(both);d['return_over_2mm'].append(copy.deepcopy(touch_row))
        check('Duplicate known TOUCH findings cannot hide an unexpected result','critical-routes',d,True)
        d=copy.deepcopy(both);d['return_over_2mm'].append({**touch_row,'id':'UNKNOWN'})
        check('Any additional unknown return remains unresolved','critical-routes',d,True)
        d=copy.deepcopy(both);d['physical_shorts']=[{'a':'TOUCH','b':'GND'}]
        check('Known TOUCH preference never hides a physical short','critical-routes',d,True)
        d=copy.deepcopy(both);d['connectivity']['N']['pass']=False
        check('Known TOUCH preference never hides a disconnected network','critical-routes',d,True)
        d=copy.deepcopy(both);d['errors']=[{'kind':'unexpected_physical_failure'}]
        check('Additional reported physical errors remain unresolved','critical-routes',d,True)
        d=copy.deepcopy(reference);d['physical_review_events'][0]['net']='TOUCH_IO_EN'
        check('TOUCH critical-route disposition is not a new CAM-plane waiver','reference-planes',d,True)
    result={'status':'PASS_REVIEW_CLASSIFIER_TESTS'if all(c['pass']for c in cases)else'FAIL_REVIEW_CLASSIFIER_TESTS','tests':cases}
    print(json.dumps(result))
    return int(any(not c['pass']for c in cases))


if __name__=='__main__':raise SystemExit(run())
