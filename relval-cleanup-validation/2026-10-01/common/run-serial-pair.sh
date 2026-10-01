#!/usr/bin/env bash
set -eo pipefail
RV_TARGET=${1:?Use jets or met}
case "$RV_TARGET" in jets|met) ;; *) exit 2 ;; esac
RV_PROJECT=/afs/cern.ch/user/m/matheus/jme-relval
RV_RELEASE=CMSSW_20_1_X_2026-09-30-2300
RV_ORIGINAL="/eos/home-m/matheus/jme-relval/$RV_RELEASE/$RV_TARGET/reference"
RV_ARCHIVE="/eos/home-m/matheus/jme-relval/$RV_RELEASE/$RV_TARGET/serial"
RV_OUTPUT="${_CONDOR_SCRATCH_DIR:?Scratch missing}/serial-results"
mkdir -p "$RV_OUTPUT/reference" "$RV_OUTPUT/candidate"
finish_pair() {
  RV_RC=$?
  trap - EXIT
  set +e
  printf '%s\n' "$RV_RC" > "$RV_OUTPUT/pair.exit-code.txt"
  date -u +%FT%TZ > "$RV_OUTPUT/finished.txt"
  cp -a "$RV_OUTPUT/." "$RV_ARCHIVE/"
  RV_COPY_RC=$?
  if [ "$RV_COPY_RC" -ne 0 ]; then exit 90; fi
  date -u +%FT%TZ > "$RV_ARCHIVE/archive-complete.txt"
  exit "$RV_RC"
}
trap finish_pair EXIT
test -d "$RV_ARCHIVE"
date -u +%FT%TZ > "$RV_ARCHIVE/worker-started.txt"
hostname > "$RV_ARCHIVE/worker-host.txt"
date -u +%FT%TZ > "$RV_OUTPUT/started.txt"
hostname > "$RV_OUTPUT/host.txt"
uname -m > "$RV_OUTPUT/machine.txt"
cat /etc/redhat-release > "$RV_OUTPUT/os.txt"
cp "$RV_ORIGINAL/reference-record.json" "$RV_OUTPUT/replay.json"
python3 - "$RV_ORIGINAL" "$RV_OUTPUT" <<'PY'
import hashlib, json, pathlib, shutil, sys
original, output = map(pathlib.Path, sys.argv[1:])
record = json.loads((output / 'replay.json').read_text())
wf = original / record['workflow_dir']
raw = wf / 'step2.root'
shutil.copy2(raw, output / 'shared-step2.root')
record.update({'original_shared_input': str(raw),
               'shared_input_sha256': hashlib.sha256((output/'shared-step2.root').read_bytes()).hexdigest(),
               'threads': 1, 'streams': 1,
               'customization': 'Both replay cfgs append numberOfThreads=1 and numberOfStreams=1; no other changes'})
for mode in ('reference', 'candidate'):
    dst = output / mode
    (dst / 'step2.root').symlink_to('../shared-step2.root')
    (dst / 'replay.json').write_text(json.dumps(record, indent=2)+'\n')
    for step in (3,4):
        name = record[f'step{step}_cfg']
        cfg = (wf / name).read_text()
        cfg += '\n# Common serial validation settings for this reference/candidate pair.\n'
        cfg += 'process.options.numberOfThreads = cms.untracked.uint32(1)\n'
        cfg += 'process.options.numberOfStreams = cms.untracked.uint32(1)\n'
        (dst / name).write_text(cfg)
(output/'replay.json').write_text(json.dumps(record, indent=2)+'\n')
PY
printf 'Starting serial reference for %s\n' "$RV_TARGET"
bash "$RV_PROJECT/run-serial-stage.sh" "$RV_TARGET" reference "$RV_OUTPUT/reference"
printf 'Starting serial candidate for %s\n' "$RV_TARGET"
bash "$RV_PROJECT/run-serial-stage.sh" "$RV_TARGET" candidate "$RV_OUTPUT/candidate"
diff -u "$RV_OUTPUT/reference/expanded-reco.py" "$RV_OUTPUT/candidate/expanded-reco.py" > "$RV_OUTPUT/expanded-reco.diff"
diff -u "$RV_OUTPUT/reference/expanded-harvest.py" "$RV_OUTPUT/candidate/expanded-harvest.py" > "$RV_OUTPUT/expanded-harvest.diff"
export SCRAM_ARCH=el9_amd64_gcc14 PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1
source /cvmfs/cms.cern.ch/cmsset_default.sh
cd "$RV_PROJECT/$RV_TARGET/$RV_RELEASE/src"
eval "$(scram runtime -sh)"
cd "$RV_OUTPUT"
set +e
python3 "$RV_PROJECT/compare-relval.py" --target "$RV_TARGET" \
  --reference reference/step3_inDQM.root --candidate candidate/step3_inDQM.root --output comparison-dqmio.json
RV_DQMIO_RC=$?
RV_REF_ROOT=$(python3 -c 'import pathlib; p=list(pathlib.Path("reference").glob("DQM*.root")); assert len(p)==1,p; print(p[0])')
RV_CAND_ROOT=$(python3 -c 'import pathlib; p=list(pathlib.Path("candidate").glob("DQM*.root")); assert len(p)==1,p; print(p[0])')
python3 "$RV_PROJECT/compare-relval.py" --target "$RV_TARGET" \
  --reference "$RV_REF_ROOT" --candidate "$RV_CAND_ROOT" --output comparison-harvested.json
RV_HARVEST_RC=$?
set -e
printf '%s\n' "$RV_DQMIO_RC" > compare-dqmio.exit-code.txt
printf '%s\n' "$RV_HARVEST_RC" > compare-harvested.exit-code.txt
test "$RV_DQMIO_RC" = 0
test "$RV_HARVEST_RC" = 0
