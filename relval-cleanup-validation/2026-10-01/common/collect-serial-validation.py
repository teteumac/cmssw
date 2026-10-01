#!/usr/bin/env python3
"""Collect the controlled serial pair without hiding earlier failed comparisons."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path

PROJECT = Path('/afs/cern.ch/user/m/matheus/jme-relval')
spec = importlib.util.spec_from_file_location('relval_collection', PROJECT/'collect-validation.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def compact_comparison(path):
    result = json.loads(path.read_text())
    return {key: result[key] for key in (
        'status', 'reference_object_count', 'candidate_object_count', 'retained_equal_count',
        'removed_keys', 'added_keys', 'changed_retained_keys')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=('jets','met'))
    args = parser.parse_args()
    release = 'CMSSW_20_1_X_2026-09-30-2300'
    validation = PROJECT/args.target/release/'relval-cleanup-validation'
    serial = validation/'serial'
    assert (serial/'archive-complete.txt').exists()
    assert (serial/'pair.exit-code.txt').read_text().strip() == '0'
    record = json.loads((serial/'replay.json').read_text())
    reports, configs, checks, diagnostics = {}, {}, {}, {}
    for mode in ('reference','candidate'):
        root = serial/mode
        for stage in ('reco','harvest'):
            assert (root/f'{stage}.exit-code.txt').read_text().strip() == '0'
            reports[f'{mode}_{stage}'] = helpers.framework_report(root/f'{stage}-job-report.xml')
        assert sum(e['events_read'] for e in reports[f'{mode}_reco']['inputs']) == 100
        assert (root/'base-sha.txt').read_text().strip() == '08c21e8297763e2aa5ad08c44a507e607e91c84b'
    assert not (serial/'reference/source.patch').read_text().strip()
    assert (serial/'candidate/source.patch').read_bytes() == (validation/'candidate.patch').read_bytes()
    assert reports['reference_reco']['metrics']['CPUModels'] == reports['candidate_reco']['metrics']['CPUModels']
    for step, expanded in ((3,'expanded-reco.py'), (4,'expanded-harvest.py')):
        name = record[f'step{step}_cfg']
        refcfg, candcfg = serial/'reference'/name, serial/'candidate'/name
        assert refcfg.read_bytes() == candcfg.read_bytes()
        assert (serial/'reference'/expanded).read_bytes() == (serial/'candidate'/expanded).read_bytes()
        configs[str(step)] = {'name':name, 'cfg_sha256':helpers.sha256(refcfg),
                              'expanded_sha256':helpers.sha256(serial/'reference'/expanded),
                              'byte_identical':True}
    gt = helpers.config_conditions(serial/'reference/expanded-reco.py')
    assert gt == helpers.config_conditions(serial/'candidate/expanded-reco.py')
    for name in ('build-reference','diff-check','build-candidate','unit-tests','checkdeps',
                 'code-checks','code-format','final-diff-check'):
        rc = int((validation/'logs'/f'{name}.exit-code.txt').read_text().strip())
        assert rc == 0, (name,rc)
        checks[name] = {'exit_code':rc, 'log':str(validation/'logs'/f'{name}.log')}
    assert (PROJECT/'serial-baseline'/args.target/'build.exit-code.txt').read_text().strip() == '0'
    checks['serial-reference-build'] = {'exit_code':0,
                                      'log':str(PROJECT/'serial-baseline'/args.target/'build.log')}
    comparisons = {name:compact_comparison(serial/f'comparison-{name}.json')
                   for name in ('dqmio','harvested')}
    for name, result in comparisons.items():
        assert result['status'] == 'PASS', name
    booking = compact_comparison(validation/'booking-candidate/comparison.json')
    assert booking['status'] == 'PASS'
    for stage in ('reco','harvest'):
        left = helpers.error_messages(serial/'reference'/f'{stage}.log')
        right = helpers.error_messages(serial/'candidate'/f'{stage}.log')
        added = set(right)-set(left)
        diagnostics[stage] = {'reference_error_categories':helpers.error_categories(left),
                              'candidate_error_categories':helpers.error_categories(right),
                              'new_error_messages':[{'severity':level,'category':category,'message':body[:1500]}
                                                    for level,category,body in sorted(added)]}
        assert not added, diagnostics[stage]
    original_reference = validation/'reference'
    original_record = json.loads((original_reference/'reference-record.json').read_text())
    assert original_record['executed_steps'] == [1,2,3,4]
    assert original_record['executed_step_exit_codes'] == [0,0,0,0]
    assert (original_reference/'reference.exit-code.txt').read_text().strip() == '0'
    original_wf = original_reference/original_record['workflow_dir']
    for step in (1,2,3,4):
        reports[f'original_reference_step{step}'] = helpers.framework_report(original_wf/f'JobReport{step}.xml')
    previous = []
    for name in ('candidate-attempt01','candidate'):
        path = validation/name/'comparison-dqmio.json'
        if not path.exists():
            continue
        result = json.loads(path.read_text())
        previous.append({'directory':name, 'threads':4, 'streams':1, 'status':result['status'],
                         'reference_host':(original_reference/'host.txt').read_text().strip(),
                         'candidate_host':(validation/name/'host.txt').read_text().strip(),
                         'removed_count':len(result['removed_keys']), 'added_count':len(result['added_keys']),
                         'changed_retained_count':len(result['changed_retained_keys']),
                         'reco_exit_code':int((validation/name/'reco.exit-code.txt').read_text().strip()),
                         'harvest_exit_code':int((validation/name/'harvest.exit-code.txt').read_text().strip())})
    dqmio = json.loads((serial/'comparison-dqmio.json').read_text())
    audit = dqmio['reference_audit']
    targets = set(json.loads((PROJECT/'selection-manifest.json').read_text())[args.target])
    monitors = {key: {item: value[item] for item in ('entries','underflow','overflow','nonzero_bins')}
                for key,value in audit['monitors'].items() if key.split(':',2)[-1] in targets}
    control_root = PROJECT/'jets'/release/'relval-cleanup-validation/four-thread-control'
    assert (control_root/'archive-complete.txt').exists()
    assert (control_root/'control.exit-code.txt').read_text().strip() == '0'
    assert (control_root/'reco.exit-code.txt').read_text().strip() == '0'
    assert not (control_root/'source.patch').read_text().strip()
    assert not (control_root/'expanded-reco.diff').read_text().strip()
    control_result = json.loads((control_root/'comparison-dqmio.json').read_text())
    control_report = helpers.framework_report(control_root/'reco-job-report.xml')
    assert sum(item['events_read'] for item in control_report['inputs']) == 100
    assert not control_result['removed_keys'] and not control_result['added_keys']
    control = {'purpose':'Unmodified four-thread RECO replay of the Jets reference input on the reference host',
               'cmsrun_exit_code':0, 'comparison_status':control_result['status'],
               'threads':4, 'streams':1, 'events_read':100,
               'host':(control_root/'host.txt').read_text().strip(),
               'cpu_models':control_report['metrics']['CPUModels'],
               'source_patch_empty':True, 'expanded_cfg_byte_identical':True,
               'shared_input_sha256':(control_root/'shared-input.sha256').read_text().split()[0],
               'removed_count':0, 'added_count':0,
               'changed_retained_count':len(control_result['changed_retained_keys']),
               'retained_entry_differences':sum(
                   control_result['reference_inventory']['objects'][key].get('entries') !=
                   control_result['candidate_inventory']['objects'][key].get('entries')
                   for key in control_result['changed_retained_keys'])}
    summary = {'target':args.target, 'status':'PASS',
               'created_utc':datetime.now(timezone.utc).isoformat(), 'release':release,
               'base_sha':'08c21e8297763e2aa5ad08c44a507e607e91c84b', 'architecture':'el9_amd64_gcc14',
               'workflow':'18434.0', 'scenario':'2026 TTbar_14TeV_TuneCP5; no additional pileup',
               'era':'Run3_2026','geometry':'DB:Extended','conditions_alias':'auto:phase1_2026_realistic',
               'resolved_globaltag':gt, 'events_requested':100,
               'reco_events_reference':100,'reco_events_candidate':100,'threads':1,'streams':1,
               'execution_backend':'CERN HTCondor EL9; reference and candidate sequentially in one allocation',
               'pair_host':(serial/'host.txt').read_text().strip(),
               'shared_input':record['original_shared_input'], 'shared_input_sha256':record['shared_input_sha256'],
               'common_validation_customization':record['customization'],
               'candidate_patch_sha256':helpers.sha256(serial/'candidate/source.patch'),
               'configs':configs,'framework_reports':reports,'checks':checks,'log_diagnostics':diagnostics,
               'comparisons':comparisons,'removed_reference_monitors':monitors,
               'muon_duplicate_pairs':audit['muon_duplicate_pairs'],
               'booking_probe':{'purpose':'Exact folder and HLT booking only; one EmptySource event',**booking},
               'original_reference':original_record,'previous_four_thread_comparisons':previous,
               'unmodified_four_thread_control':control,
               'reproduction_observation':'Four-thread full RECO replays changed retained CHS/associated MET MEs; '
                                         'the controlled serial pair is the strict acceptance comparison. '
                                         'No reconstruction or selection code was changed.',
               'broader_limited_matrix_executed':False,
               'scope_limit':'100-event technical validation; broader physics validation and central CI remain separate'}
    (validation/'validation-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({key:summary[key] for key in ('target','status','resolved_globaltag','pair_host','comparisons',
                                                  'removed_reference_monitors','log_diagnostics',
                                                  'previous_four_thread_comparisons')},indent=2))


if __name__ == '__main__':
    main()
