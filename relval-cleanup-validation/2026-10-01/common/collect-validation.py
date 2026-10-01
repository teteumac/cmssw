#!/usr/bin/env python3
"""Summarize only results produced by these two RelVal validation areas."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def framework_report(path):
    root = ET.parse(path).getroot()
    errors = [ET.tostring(e, encoding="unicode") for e in root.findall("FrameworkError")]
    if errors:
        raise RuntimeError(f"Framework errors in {path}: {errors}")
    inputs = [{"pfn": e.findtext("PFN"), "source_class": e.findtext("InputSourceClass"),
               "events_read": int(e.findtext("EventsRead", "0"))}
              for e in root.findall("InputFile")]
    outputs = [{"pfn": e.findtext("PFN"), "module_class": e.findtext("OutputModuleClass"),
                "total_events": int(e.findtext("TotalEvents", "0"))}
               for e in root.findall("File")]
    metrics = {e.attrib["Name"]: e.attrib.get("Value") for e in root.findall(".//Metric")
               if e.attrib.get("Name") in ("NumberEvents", "CPUModels", "NumberThreads", "NumberStreams")}
    return {"file": str(path), "process": root.findtext("Process/Name"),
            "inputs": inputs, "outputs": outputs, "metrics": metrics}


def config_conditions(path):
    # Geometry makes these dumps tens of MB; only the resolved literal is needed.
    found = [match[1] for match in re.findall(
        r'\bglobaltag\s*=\s*cms\.string\(\s*([\'"])([^\'"\n]+)\1\s*\)', path.read_text())]
    if len(found) != 1:
        raise RuntimeError(f"Expected exactly one resolved GlobalTag in {path}: {found}")
    return found[0]


def error_messages(path):
    messages = Counter()
    source = re.sub(r'(root://[^\s?]+)\?[^\s]*', r'\1?[access parameters redacted]', path.read_text())
    for level, category, header, body in re.findall(
            r'%MSG-([es])\s+([^:\n]+):([^\n]*)\n(.*?)\n%MSG', source, re.S):
        messages[(level, category.strip(), body.strip())] += 1
    return messages


def error_categories(messages):
    counts = Counter()
    for (level, category, body), count in messages.items():
        counts[f"{level}:{category}"] += count
    return dict(sorted(counts.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("jets", "met"))
    args = parser.parse_args()
    release = "CMSSW_20_1_X_2026-09-30-2300"
    area = Path("/afs/cern.ch/user/m/matheus/jme-relval") / args.target / release
    validation = area / "relval-cleanup-validation"
    reference, candidate = validation / "reference", validation / "candidate"
    refrecord = json.loads((reference / "reference-record.json").read_text())
    wf = reference / refrecord["workflow_dir"]
    replay = json.loads((candidate / "replay.json").read_text())
    for stage, root in (("reference", reference), ("candidate", candidate)):
        assert (root / f"{stage}.exit-code.txt").read_text().strip() == "0", stage
    reports = {f"reference_step{step}": framework_report(wf / f"JobReport{step}.xml")
               for step in (1, 2, 3, 4)}
    reports["candidate_reco"] = framework_report(candidate / "reco-job-report.xml")
    reports["candidate_harvest"] = framework_report(candidate / "harvest-job-report.xml")
    for name in ("reference_step2", "reference_step3", "candidate_reco"):
        assert sum(e["events_read"] for e in reports[name]["inputs"]) == 100, name
    assert any(e["total_events"] == 100 for e in reports["reference_step1"]["outputs"])
    configs = {}
    for step, expanded in ((3, "expanded-reco.py"), (4, "expanded-harvest.py")):
        refcfg = wf / refrecord[f"step{step}_cfg"]
        candcfg = candidate / replay["configs"][str(step)]["name"]
        assert refcfg.read_bytes() == candcfg.read_bytes(), (refcfg, candcfg)
        assert (reference / expanded).read_bytes() == (candidate / expanded).read_bytes(), expanded
        configs[str(step)] = {"reference": str(refcfg), "candidate": str(candcfg),
                              "cfg_sha256": sha256(refcfg),
                              "expanded_sha256": sha256(reference / expanded),
                              "byte_identical": True}
    gt = config_conditions(reference / "expanded-reco.py")
    assert gt == config_conditions(candidate / "expanded-reco.py")
    checks = {}
    for name in ("build-reference", "diff-check", "build-candidate", "unit-tests", "checkdeps",
                 "code-checks", "code-format", "final-diff-check"):
        rc = int((validation / "logs" / f"{name}.exit-code.txt").read_text().strip())
        assert rc == 0, (name, rc)
        checks[name] = {"exit_code": rc, "log": str(validation / "logs" / f"{name}.log")}
    checks["build-after-checks"] = {
        "executed": (validation / "logs/build-after-checks.exit-code.txt").exists(),
        "reason_if_omitted": "No code or checked-out dependencies changed after the completed build",
    }
    comparisons = {}
    for name in ("dqmio", "harvested"):
        result = json.loads((candidate / f"comparison-{name}.json").read_text())
        assert result["status"] == "PASS", (name, result["status"])
        comparisons[name] = {key: result[key] for key in (
            "status", "reference_object_count", "candidate_object_count", "retained_equal_count",
            "removed_keys", "added_keys", "changed_retained_keys")}
    booking = json.loads((validation / "booking-candidate/comparison.json").read_text())
    assert booking["status"] == "PASS"
    diagnostics = {}
    for step, stage in ((3, "reco"), (4, "harvest")):
        logs = list(wf.glob(f"step{step}_*.log"))
        assert len(logs) == 1, logs
        left = error_messages(logs[0])
        right = error_messages(candidate / f"{stage}-candidate.log")
        added = set(right) - set(left)
        diagnostics[stage] = {
            "reference_error_categories": error_categories(left),
            "candidate_error_categories": error_categories(right),
            "new_error_messages": [{"severity": level, "category": category, "message": body[:1500]}
                                   for level, category, body in sorted(added)],
        }
        assert not added, diagnostics[stage]
    summary = {
        "target": args.target, "created_utc": datetime.now(timezone.utc).isoformat(),
        "release": release, "base_sha": (validation / "base-sha.txt").read_text().strip(),
        "architecture": "el9_amd64_gcc14", "workflow": "18434.0",
        "scenario": "2026 TTbar_14TeV_TuneCP5; no additional pileup",
        "era": "Run3_2026", "geometry": "DB:Extended",
        "conditions_alias": "auto:phase1_2026_realistic", "resolved_globaltag": gt,
        "events_requested": 100, "reco_events_reference": 100, "reco_events_candidate": 100,
        "threads": 4, "streams": 1,
        "execution_backend": "CERN HTCondor EL9; four CPUs requested, no GPUs requested",
        "hosts": {stage: (root / "host.txt").read_text().strip()
                  for stage, root in (("reference", reference), ("candidate", candidate))},
        "shared_input": replay["shared_input"],
        "shared_input_checksum": (candidate / "shared-input.sha256").read_text().strip(),
        "configs": configs, "framework_reports": reports, "checks": checks,
        "log_diagnostics": diagnostics,
        "comparisons": comparisons,
        "booking_probe": {"purpose": "Exact folder and HLT booking only; one EmptySource event",
                          "status": booking["status"], "removed_keys": booking["removed_keys"],
                          "retained_equal_count": booking["retained_equal_count"]},
        "broader_limited_matrix_executed": False,
        "scope_limit": "100-event technical validation; broader physics validation and central CI remain separate",
    }
    (validation / "validation-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("configs", "framework_reports", "checks")}, indent=2))


if __name__ == "__main__":
    main()
