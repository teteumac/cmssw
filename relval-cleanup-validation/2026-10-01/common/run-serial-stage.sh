#!/usr/bin/env bash
set -eo pipefail
RV_TARGET=${1:?Use jets or met}
RV_MODE=${2:?Use reference or candidate}
RV_OUTPUT=${3:?Working directory required}
case "$RV_TARGET" in jets|met) ;; *) exit 2 ;; esac
RV_PROJECT=/afs/cern.ch/user/m/matheus/jme-relval
RV_RELEASE=CMSSW_20_1_X_2026-09-30-2300
case "$RV_MODE" in
  reference) RV_AREA="$RV_PROJECT/serial-baseline/$RV_TARGET/$RV_RELEASE" ;;
  candidate) RV_AREA="$RV_PROJECT/$RV_TARGET/$RV_RELEASE" ;;
  *) exit 2 ;;
esac
export PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1 SCRAM_ARCH=el9_amd64_gcc14
source /cvmfs/cms.cern.ch/cmsset_default.sh
cd "$RV_AREA/src"
eval "$(scram runtime -sh)"
git rev-parse HEAD > "$RV_OUTPUT/base-sha.txt"
git diff > "$RV_OUTPUT/source.patch"
git status --short > "$RV_OUTPUT/git-status.txt"
printf '%s\n' "$CMSSW_BASE" > "$RV_OUTPUT/build-area.txt"
printf '%s\n' "$SCRAM_ARCH" > "$RV_OUTPUT/architecture.txt"
cd "$RV_OUTPUT"
RV_RECO=$(python3 -c 'import json; print(json.load(open("replay.json"))["step3_cfg"])')
RV_HARVEST=$(python3 -c 'import json; print(json.load(open("replay.json"))["step4_cfg"])')
edmConfigDump "$RV_RECO" > expanded-reco.py
edmConfigDump "$RV_HARVEST" > expanded-harvest.py
printf 'cmsRun -j reco-job-report.xml %s\ncmsRun -j harvest-job-report.xml %s\n' "$RV_RECO" "$RV_HARVEST" > commands.txt
for RV_STAGE in reco harvest; do
  case "$RV_STAGE" in reco) RV_CFG=$RV_RECO ;; harvest) RV_CFG=$RV_HARVEST ;; esac
  printf '%s: %s %s started\n' "$(date -u +%FT%TZ)" "$RV_MODE" "$RV_STAGE"
  date -u +%FT%TZ > "$RV_STAGE.started.txt"
  set +e
  cmsRun -j "$RV_STAGE-job-report.xml" "$RV_CFG" > "$RV_STAGE.log" 2>&1
  RV_RC=$?
  set -e
  printf '%s\n' "$RV_RC" > "$RV_STAGE.exit-code.txt"
  date -u +%FT%TZ > "$RV_STAGE.finished.txt"
  printf '%s: %s %s exit %s\n' "$(date -u +%FT%TZ)" "$RV_MODE" "$RV_STAGE" "$RV_RC"
  test "$RV_RC" = 0
done
