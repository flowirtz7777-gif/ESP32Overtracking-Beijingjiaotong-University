const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const ROOT=path.resolve(__dirname,'..'),file=path.join(ROOT,'plan.json');
const p=JSON.parse(fs.readFileSync(file,'utf8'));
assert(['planned_not_started','implementation_in_progress','running','checkpoint_saved','complete'].includes(p.status));
assert.equal(typeof p.new_experiments_started,'boolean');
assert.equal(typeof p.execution_authorized_now,'boolean');
assert.equal(p.driving_factors.speed_definition,'tractor_rear_axle_longitudinal_v_B');
assert.equal(p.vehicle.truth_phi_clamping_allowed,false);
assert(p.targets.formal_target_count==null||p.targets.formal_target_count>=p.targets.minimum_formal_target_count);
assert(p.targets.same_coordinates_and_labels_per_trajectory_across_algorithms);
assert(p.targets.interior_points_kept);
assert.equal(p.targets.ignored_first_contact_edge,'FRONT');
assert.equal(p.evaluation.common_end_exclude_s,p.evaluation.max_formal_horizon_s);
assert(p.evaluation.own_window_and_common_reference_metrics_both_required);
assert.equal(p.evaluation.common_reference_horizon_s,p.core_comparison.W_s);
assert(p.joint_processing.EXIT_W_s.every(w=>w>=p.joint_processing.A_s&&w<=p.evaluation.max_formal_horizon_s));
assert(p.joint_processing.A_s>=p.joint_processing.I_s);
const scenarios=[];
for(const speed of p.driving_factors.v_B_mps)for(const rate of p.driving_factors.base_rate_deg_s)
  for(const t of p.driving_factors.templates)scenarios.push({
    id:'v'+speed+'_r'+rate+'_'+t.id,status:'design_only_not_generated',v_B_mps:speed,
    base_rate_deg_s:rate,template:t.id,entry_rate_abs_deg_s:rate*t.entry_rate_multiplier,
    return_rate_abs_deg_s:rate*t.return_rate_multiplier,
    alpha_peak_abs_deg:p.driving_factors.alpha_peak_abs_deg,
    trajectory_feasibility:'pending_S0',turn_heading_change_deg:p.scope.right_turn_heading_change_deg});
assert.equal(scenarios.length,p.driving_factors.nominal_factorial_trajectories);
assert.equal(new Set(scenarios.map(x=>x.id)).size,scenarios.length);
assert.equal(scenarios.length*p.methods.length,p.core_comparison.nominal_prediction_jobs);
const joint=[];
for(let method=1;method<=p.joint_processing.finalist_method_count;method++)
  for(const w of p.joint_processing.EXIT_W_s)for(const margin of p.joint_processing.margin_m)
    for(const confirmation of p.joint_processing.confirmation_s)joint.push({
      id:'f'+method+'_w'+w+'_m'+Math.round(margin*1000)+'_c'+Math.round(confirmation*1000),
      method_slot:method,method_id:null,status:'design_only_not_executed',default_W_s:p.joint_processing.default_W_s,
      EXIT_W_s:w,margin_m:margin,confirmation_s:confirmation});
assert.equal(joint.length,p.joint_processing.nominal_configurations);
assert.equal(joint.length*p.joint_processing.optional_gain.length,
  p.joint_processing.maximum_effective_configurations_with_gain);
function frozenDesign(name,value) {
  const target=path.join(ROOT,name);
  if(fs.existsSync(target))assert.deepEqual(JSON.parse(fs.readFileSync(target,'utf8')),value);
  else fs.writeFileSync(target,JSON.stringify(value,null,2)+'\n');
}
frozenDesign('scenario_matrix.json',scenarios);frozenDesign('joint_matrix.json',joint);
const check={status:'plan_consistency_passed',design_scenarios:scenarios.length,
  nominal_core_jobs:p.core_comparison.nominal_prediction_jobs,joint_configs:joint.length,
  experiments_executed_by_this_validator:0};
const activeCheckpoint=path.join(ROOT,'runs','overnight_20261014_v3','checkpoint.json');
if(fs.existsSync(activeCheckpoint)) {
  const cp=JSON.parse(fs.readFileSync(activeCheckpoint,'utf8'));
  check.active_run='overnight_20261014_v3';
  check.completed_prediction_jobs_in_active_checkpoint=Object.keys(cp.completed).length;
  check.completed_stage_records=cp.stages;
  check.checkpoint_read_time=new Date().toISOString();
}
if(p.legacy_archive.state==='archived_verified') {
  const verification=JSON.parse(fs.readFileSync(path.resolve(ROOT,p.legacy_archive.snapshot_directory,'verification.json'),'utf8'));
  assert.equal(verification.status,'verified');
  assert.equal(verification.zip_entry_hashes_verified,verification.legacy_file_count);
  assert.equal(verification.original_hashes_rechecked,verification.legacy_file_count);
  assert.equal(verification.readonly_file_count,verification.legacy_file_count);
  check.legacy_archive_verified_files=verification.legacy_file_count;
}
fs.writeFileSync(path.join(ROOT,'planning_validation.json'),JSON.stringify(check,null,2)+'\n');
console.log(JSON.stringify(check));
