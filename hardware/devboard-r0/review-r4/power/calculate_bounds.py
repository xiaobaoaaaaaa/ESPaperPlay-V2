"""r4 source-backed bounds and explicitly unverified engineering allocations."""
from pathlib import Path
import json
HERE=Path(__file__).resolve().parent
def divider(top,bottom,tol,tcr,aging=0):
    # +/-100nA is a conservative bound; TI specifies IFB max100nA.
    e=tol+tcr*65+aging
    return {'top_ohm':top,'bottom_ohm':bottom,'resistor_combined_fraction':e,
      'pwm_vout_min_v':.495*(1+top*(1-e)/(bottom*(1+e)))-100e-9*top*(1+e),
      'pwm_vout_max_v':.505*(1+top*(1+e)/(bottom*(1-e)))+100e-9*top*(1+e),
      'nominal_vout_v':.5*(1+top/bottom),'divider_current_at_3v3_a':3.3/(top+bottom)}
old=divider(511000,91000,.01,100e-6)
new=divider(51100,9100,.001,25e-6,.001)
# Independent review: include external 1% / 100ppm resistors over -40..85C.
# BQ table guarantees themselves apply only at the stated TJ=0..125C.
bq_r_error=.01+100e-6*65
bq_r_min=.99*(1-100e-6*65);bq_r_max=1.01*(1+100e-6*65)
ilow=1500/(1620*bq_r_max);ihigh=1720/(1620*bq_r_min)
ichg_min=797/(3000*bq_r_max);ichg_max=975/(3000*bq_r_min);ichg_typ=890/3000
bypass=.005 # project allowance, not a measured leakage current
fuse_load=ihigh+bypass
data={'date':'2026-11-02','sources':[
 {'url':'https://www.ti.com/lit/ds/symlink/tps63802.pdf','local_path':'hardware/reference/power/tps63802.pdf','sections':'8.5 VFB +/-1% PWM, IFB max100nA;10.2.2.5'},
 {'url':'https://www.vishay.com/docs/28758/tnpw_e3.pdf','local_path':'hardware/reference/closure-r4/files/tnpw_e3.pdf','sections':'pp2-4;0603 B0.1% E25ppm EA5000'},
 {'url':'https://www.ti.com/lit/ds/symlink/bq24074.pdf','local_path':'hardware/reference/power/bq24074.pdf','sections':'pp10/12/13;KILIM1500..1720,KISET797..975,KTMR36..60s/kohm,RTMR18..72kohm'},
 {'url':'https://www.bourns.com/docs/product-datasheets/mf-msmf.pdf','local_path':'hardware/reference/mcu-usb/bourns-mf-msmf.pdf','sections':'MF-MSMF200/16X,thermal table50C1.68A/60C1.48A,Style2/Hmax1.60mm'},
 ],'feedback':{'temperature_design_range_c':[-40,85],'reference_temp_c':25,'aging_allocation_fraction':.001,'aging_note':'Project allowance per resistor, consistent with TNPW standard-load8000h table; not lifetime qualification.','old':old,'new':new,'additional_3v3_current_a':new['divider_current_at_3v3_a']-old['divider_current_at_3v3_a'],'result':'PASS calculated PWM component-error budget against3.201..3.399V; PFM ripple/line-load response/PCB effects still require measurement.'},
 'usb_fuse':{'old_mpn':'MF-MSMF110/16X-2','new_mpn':'MF-MSMF200/16X-2','rlim_ohm':1620,'ilim_min_a':ilow,'ilim_typ_a':1610/1620,'ilim_max_a':ihigh,'unmeasured_bypass_allocation_a':bypass,'allocated_fuse_load_a':fuse_load,'ihold_at_50c_a':1.68,'ihold_at_60c_a':1.48,'fraction_at_50c':fuse_load/1.68,'fraction_at_60c':fuse_load/1.48,'r1max_23c_ohm':.07,'drop_r1max_23c_v':fuse_load*.07,'dissipation_r1max_23c_w':fuse_load**2*.07,'connector_evidence':'USB4105 drawing:5A totalVBUS. J502 Wurth61300311121:3A/contact. Supply/cable/wires/PCB fault tests remain separate.','qualification':'Hold-current selection mismatch closed at50/60C using catalog table. Not short-circuit/TVS coordination, precise fuse limit, high-temperature Rmax or source authorization proof. DefaultUSB100 unchanged; high-mode only with approved source.'},
 'user_battery':{'model':'ZON.CELL755570','capacity_ah':4.0,'nominal_voltage_v':3.7,'nominal_energy_wh':14.8,'evidence':'User screenshot, not independently obtained pack datasheet.','advertised_continuous_a':2.0,'advertised_continuous_temp_c':[10,55],'advertised_cold_a':.8,'advertised_cold_temp_c':[-10,10],'advertised_peak_a':3,'advertised_peak_temp_c':[10,45],'peak_duration_s':None,'initial_board_test_temp_c':[20,30],'initial_main_3v3_a':1,'audio_output_design_cap_w':.5,'assumed_reg_efficiency':.85,'assumed_amp_efficiency':.85,'assumed_sys_floor_v':2.9,'other_battery_current_allocation_a':.05},
 'charging':{'iset_ohm':3000,'ichg_min_a':ichg_min,'ichg_typ_a':ichg_typ,'ichg_max_a':ichg_max,'rtmr_ohm':68000,'timer_min_h':10*36*68*.99/3600,'timer_typ_h':10*48*68/3600,'timer_max_h':10*60*68*1.01/3600,'ideal_full_capacity_over_typ_current_h':4/ichg_typ,'status':'NOT QUALIFIED: selected4000mAh pack makes old297mA/timer9.07h pair suspect. Capacity/current quotient is not full CC/CV charge time and timer stretches under DPPM/thermal regulation. Do not increaseRTMR above72kohm, disabletimer or cycleCE. Need actual pack charge current/temp/NTC data and charging profile before choosing newISET/TMR. R108 staysDNP.'}}
data['charging']['timer_min_h']=10*36*68*bq_r_min/3600
data['charging']['timer_max_h']=10*60*68*bq_r_max/3600
data['bq_bound_conditions']={'external_resistor_initial_tolerance':.01,'external_resistor_tcr_ppm_C':100,'external_resistor_temperature_C':[-40,85],'external_resistor_min_factor':bq_r_min,'external_resistor_max_factor':bq_r_max,'bq_table_junction_temperature_C':[0,125],'qualification':'Electrical table bounds are conditional on BQ TJ being within0..125C. No -40C BQ operation, board thermal or charging-temperature approval is implied; external resistor aging remains unqualified.'}
b=data['user_battery']
b['estimated_initial_battery_a']=3.3*b['initial_main_3v3_a']/(.85*2.9)+.5/(.85*2.9)+.05
b['estimated_main_1_5a_pulse_plus_audio_a']=3.3*1.5/(.85*2.9)+.5/(.85*2.9)+.05
b['qualification']='Allocations are initial test limits, not measured peak demand/efficiency or firmware limits.1.5A/100ms main-rail target remains a bench-source test until3A pack pulse duration/protection are known. Below10C no full-load approval. No temperature measurement fromTS toMCU exists yet.'
assert 3.201 <= new['pwm_vout_min_v'] and new['pwm_vout_max_v'] <=3.399
assert fuse_load<.8*1.48
assert b['estimated_initial_battery_a']<2
(HERE/'power-bounds.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'pwm_vout':[new['pwm_vout_min_v'],new['pwm_vout_max_v']],'fuse_allocated_a':fuse_load,'battery_initial_a':b['estimated_initial_battery_a'],'timer_h':[data['charging'][k] for k in ['timer_min_h','timer_typ_h','timer_max_h']]},indent=2))
