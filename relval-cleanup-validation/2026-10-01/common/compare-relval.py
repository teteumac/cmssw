#!/usr/bin/env python3
"""Strict RelVal ME comparison for DQMIO and harvested ROOT.

Histogram snapshots reuse the independently validated Offline DQM comparison
implementation. This tool preserves run/lumi scopes and uses an explicit RelVal
removal manifest. Run with the CMSSW PyROOT runtime.
"""
import argparse
from array import array
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

class InputError(RuntimeError):
    pass


def number(value):
    """Lossless double representation, including signed zero and nonfinite values."""
    return float(value).hex()


def raw_number(value):
    # TH1L and integer histogram accumulators must not lose precision through
    # a conversion to double when their storage contains values above 2**53.
    return f"int:{value}" if isinstance(value, int) else number(value)


def root_array(values):
    return [number(values.At(i)) for i in range(values.GetSize())]


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def axis_snapshot(axis):
    nbins = int(axis.GetNbins())
    return {
        "title": str(axis.GetTitle()),
        "nbins": nbins,
        "min": number(axis.GetXmin()),
        "max": number(axis.GetXmax()),
        "edges": [number(axis.GetBinLowEdge(i)) for i in range(1, nbins + 2)],
        "bin_low_edges_with_flows": [number(axis.GetBinLowEdge(i)) for i in range(nbins + 3)],
        "variable_edges": root_array(axis.GetXbins()),
        "labels": [str(axis.GetBinLabel(i)) for i in range(nbins + 2)],
        "first": int(axis.GetFirst()),
        "last": int(axis.GetLast()),
        "range_set": bool(axis.TestBit(axis.kAxisRange)),
    }


def serialized_object(obj, ROOT):
    value = ROOT.TBufferJSON.ConvertToJSON(obj)
    if not value:
        raise InputError(f"Cannot serialize ROOT object of class {obj.ClassName()}")
    return str(value.Data())


def histogram_snapshot(hist, ROOT):
    """Include every global cell: under/overflow in all dimensions as well."""
    ncells = int(hist.GetNcells())
    if not hasattr(hist, "GetArray"):
        raise InputError(f"Unsupported histogram storage: {hist.ClassName()}/{hist.GetName()}")
    stats = array("d", [0.0] * int(ROOT.TH1.kNstat))
    hist.GetStats(stats)
    result = {
        "class": str(hist.ClassName()),
        "name": str(hist.GetName()),
        "title": str(hist.GetTitle()),
        "dimension": int(hist.GetDimension()),
        "ncells": ncells,
        "axes": [axis_snapshot(axis) for axis in (hist.GetXaxis(), hist.GetYaxis(), hist.GetZaxis())],
        "entries": number(hist.GetEntries()),
        "effective_entries": number(hist.GetEffectiveEntries()),
        "stats": [number(value) for value in stats],
        "contents": [number(hist.GetBinContent(i)) for i in range(ncells)],
        "errors": [number(hist.GetBinError(i)) for i in range(ncells)],
        "sumw2": root_array(hist.GetSumw2()),
        "raw_array": [raw_number(hist.GetArray()[i]) for i in range(ncells)],
        "norm_factor": number(hist.GetNormFactor()),
        "bin_error_option": int(hist.GetBinErrorOption()),
        "functions": [serialized_object(obj, ROOT) for obj in hist.GetListOfFunctions()],
    }
    if hasattr(hist, "GetStatOverflowsBehaviour"):
        result["stat_overflows_behaviour"] = int(hist.GetStatOverflowsBehaviour())
    if any(hist.InheritsFrom(cls) for cls in ("TProfile", "TProfile2D", "TProfile3D")):
        result["profile"] = {
            "error_option": str(hist.GetErrorOption()),
            "bin_entries": [number(hist.GetBinEntries(i)) for i in range(ncells)],
            "bin_effective_entries": [number(hist.GetBinEffectiveEntries(i)) for i in range(ncells)],
            "bin_sumw2": root_array(hist.GetBinSumw2()),
        }
        for limit in ("GetYmin", "GetYmax", "GetZmin", "GetZmax", "GetTmin", "GetTmax"):
            if hasattr(hist, limit):
                result["profile"][limit] = number(getattr(hist, limit)())
    return result


def nonfinite_fields(value, prefix=""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from nonfinite_fields(child, f"{prefix}.{key}" if prefix else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from nonfinite_fields(child, f"{prefix}[{index}]")
    elif value in ("nan", "inf", "-inf"):
        yield prefix


def compact_value(value):
    if isinstance(value, str) and len(value) > 240:
        return {"type": "string", "length": len(value), "prefix": value[:240]}
    if isinstance(value, (list, dict)):
        return {"type": type(value).__name__, "length": len(value)}
    return value


def differences(reference, candidate, limit=12):
    """Count all differences; retain only bounded diagnostic samples."""
    samples = []
    counts = Counter()

    def record(location, left, right):
        section = location.lstrip(".").split(".", 1)[0].split("[", 1)[0]
        counts[section] += 1
        if len(samples) < limit:
            samples.append({"field": location.lstrip("."), "reference": compact_value(left), "candidate": compact_value(right)})

    def visit(left, right, location):
        if left == right:
            return
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                visit(left.get(key, "<missing>"), right.get(key, "<missing>"), f"{location}.{key}")
        elif isinstance(left, list) and isinstance(right, list):
            if len(left) != len(right):
                record(f"{location}.length", len(left), len(right))
            for index in range(max(len(left), len(right))):
                a = left[index] if index < len(left) else "<missing>"
                b = right[index] if index < len(right) else "<missing>"
                visit(a, b, f"{location}[{index}]")
        else:
            record(location, left, right)

    visit(reference, candidate, "")
    return {"changed_fields": sum(counts.values()), "counts_by_section": dict(sorted(counts.items())), "examples": samples}


def latest_keys(directory):
    keys = {}
    older_cycles = []
    for key in directory.GetListOfKeys():
        name = str(key.GetName())
        previous = keys.get(name)
        if previous is None or key.GetCycle() > previous.GetCycle():
            if previous is not None:
                older_cycles.append({"name": name, "cycle": int(previous.GetCycle())})
            keys[name] = key
        else:
            older_cycles.append({"name": name, "cycle": int(key.GetCycle())})
    return [keys[name] for name in sorted(keys)], older_cycles


def logical_path(storage_path):
    match = re.fullmatch(r"DQMData/Run (\d+)/([^/]+)/Run summary(?:/(.*))?", storage_path)
    if match:
        run, subsystem, tail = match.groups()
        return subsystem + (f"/{tail}" if tail else ""), int(run)
    return storage_path, None


# DQMServices/FwkIO/plugins/format.h at the recorded base SHA.
DQMIO_TYPES = ["Ints", "Floats", "Strings", "TH1Fs", "TH1Ss", "TH1Ds",
               "TH2Fs", "TH2Ss", "TH2Ds", "TH2Polys", "TH3Fs", "TProfiles",
               "TProfile2Ds", "TH1Is", "TH2Is"]
JET_PREFIX = "JetMET/JetValidation/"
MET_PREFIX = "JetMET/METValidation/caloMet/"
REMOVALS = {
    "jets": [JET_PREFIX + name for name in (
        "ak4PFJets/chargedMuEnergy", "ak4PFJets/chargedMuEnergyFraction",
        "ak4CaloJets/n60", "ak4CaloJets/n90")],
    "met": [MET_PREFIX + name for name in ("CaloSETInmHF", "CaloSETInpHF")],
}
PRESERVED = [JET_PREFIX + "ak4PFJets/" + name for name in (
    "muonEnergy", "muonEnergyFraction", "muonMultiplicity",
    "chargedHadronMultiplicity", "chargedMultiplicity", "electronMultiplicity")]
PRESERVED += [JET_PREFIX + "ak4PFJets/" + name + "_" + region
              for name in ("chargedHadronMultiplicity", "chargedMultiplicity", "electronMultiplicity")
              for region in ("B", "E", "F")]
PRESERVED += [JET_PREFIX + "slimmedJetsPuppi/" + name for name in ("HadronFlavor", "PartonFlavor")]
AUDIT_PATHS = set(REMOVALS["jets"] + REMOVALS["met"] + PRESERVED)


def in_scope(path):
    return path.startswith(("JetMET/", "HLT/JetMET/"))


def possibly_in_scope(storage_path):
    """Prune unrelated ROOT directories before deserializing their objects."""
    if storage_path == "DQMData" or re.fullmatch(r"DQMData/Run \d+", storage_path):
        return True
    if re.fullmatch(r"DQMData/Run \d+/(?:JetMET|HLT)(?:/Run summary)?", storage_path):
        return True
    path, _ = logical_path(storage_path)
    return path in ("JetMET", "HLT", "HLT/JetMET") or in_scope(path)


def read_file(filename, ROOT):
    handle = ROOT.TFile.Open(str(filename), "READ")
    if not handle or handle.IsZombie() or handle.TestBit(ROOT.TFile.kRecovered):
        raise InputError(f"Cannot read intact ROOT file: {filename}")
    objects, audit = {}, {}
    kind = "DQMIO" if handle.Get("Indices") else "harvested"
    excluded = Counter()

    def add(path, run, lumi, snapshot, flags=None):
        key = f"{run}:{lumi}:{path}"
        if key in objects:
            raise InputError(f"Duplicate ME in the same run/lumi scope: {key}")
        state = {"snapshot": snapshot}
        if flags is not None:
            state["flags"] = flags
        record = {"path": path, "run": run, "lumi": lumi,
                  "class": snapshot["class"], "sha256": digest(state)}
        if "entries" in snapshot:
            record.update(entries=snapshot["entries"], ncells=snapshot["ncells"])
        if flags is not None:
            record["flags"] = flags
        objects[key] = record
        if path in AUDIT_PATHS:
            audit[key] = {**record, "snapshot": snapshot}

    try:
        if kind == "DQMIO":
            indices = handle.Get("Indices")
            for index in indices:
                typ = int(index.Type)
                if typ == 1000:  # kNoTypesStored
                    continue
                if not 0 <= typ < len(DQMIO_TYPES):
                    raise InputError(f"Unknown DQMIO type {typ}")
                tree = handle.Get(DQMIO_TYPES[typ])
                if not tree:
                    raise InputError(f"Missing DQMIO tree {DQMIO_TYPES[typ]}")
                run, lumi = int(index.Run), int(index.Lumi)
                for position in range(int(index.FirstIndex), int(index.LastIndex) + 1):
                    if tree.GetEntry(position) <= 0:
                        raise InputError(f"Unreadable DQMIO entry {position}")
                    path = str(tree.FullName)
                    if not in_scope(path):
                        excluded[path.split("/", 1)[0]] += 1
                        continue
                    if typ >= 3:
                        snapshot = histogram_snapshot(tree.Value, ROOT)
                    elif typ == 0:
                        snapshot = {"class": "DQMIO::Int", "value": int(tree.Value)}
                    elif typ == 1:
                        snapshot = {"class": "DQMIO::Float", "value": number(tree.Value)}
                    else:
                        snapshot = {"class": "DQMIO::String", "value": str(tree.Value)}
                    add(path, run, lumi, snapshot, int(tree.Flags))
        else:
            def walk(directory, parent=""):
                keys, older = latest_keys(directory)
                if older:
                    raise InputError(f"Multiple ROOT key cycles require explicit review: {parent}")
                for key in keys:
                    storage_path = f"{parent}/{key.GetName()}" if parent else str(key.GetName())
                    if not possibly_in_scope(storage_path):
                        excluded[storage_path.split("/", 1)[0]] += 1
                        continue
                    obj = key.ReadObj()
                    if not obj:
                        raise InputError(f"Unreadable object {storage_path}")
                    if obj.InheritsFrom("TDirectory"):
                        walk(obj, storage_path)
                        continue
                    path, run = logical_path(storage_path)
                    if not in_scope(path):
                        excluded[path.split("/", 1)[0]] += 1
                        continue
                    if obj.InheritsFrom("TH1"):
                        snapshot = histogram_snapshot(obj, ROOT)
                    elif obj.InheritsFrom("TObjString"):
                        snapshot = {"class": str(obj.ClassName()), "string": str(obj.GetString().Data())}
                    else:
                        snapshot = {"class": str(obj.ClassName()), "json": serialized_object(obj, ROOT)}
                    add(path, run, 0, snapshot)
            walk(handle)
    finally:
        handle.Close()
    if not objects:
        raise InputError(f"No JetMET or HLT/JetMET MEs in {filename}")
    return {"file": str(Path(filename).resolve()), "format": kind, "objects": objects,
            "audit": audit, "excluded_subsystems": dict(excluded),
            "excluded_count_basis": "ME records" if kind == "DQMIO" else "Pruned keys and directories"}


def reference_audit(data, target):
    paths = {record["path"] for record in data["objects"].values()}
    result = {"missing_removal_targets": sorted(set(REMOVALS[target]) - paths),
              "missing_preserved_monitors": sorted(set(PRESERVED) - paths),
              "monitors": {}, "muon_duplicate_pairs": []}
    for key, record in data["audit"].items():
        snap = record["snapshot"]
        if "contents" not in snap:
            continue
        bins = [float.fromhex(value) for value in snap["contents"]]
        result["monitors"][key] = {
            "entries": float.fromhex(snap["entries"]), "underflow": bins[0],
            "overflow": bins[-1], "bin_contents_including_flows": bins,
            "axis": snap["axes"][0], "stats": snap["stats"],
            "nonzero_bins": [i for i, content in enumerate(bins) if content != 0],
        }
    if target == "jets":
        for name in ("Energy", "EnergyFraction"):
            old = JET_PREFIX + "ak4PFJets/chargedMu" + name
            new = JET_PREFIX + "ak4PFJets/muon" + name
            for key, record in data["audit"].items():
                if record["path"] != old:
                    continue
                other_key = f'{record["run"]}:{record["lumi"]}:{new}'
                if other_key not in data["audit"]:
                    raise InputError(f"Missing survivor for muon duplicate pair {key}")
                left = dict(record["snapshot"])
                right = dict(data["audit"][other_key]["snapshot"])
                for presentation in ("name", "title"):
                    left.pop(presentation, None)
                    right.pop(presentation, None)
                # Booking differs only in name/title; axes and all numerical state stay exact.
                bin_values = [float.fromhex(value) for value in left["contents"]]
                result["muon_duplicate_pairs"].append({
                    "removed": key, "survivor": other_key, "equal_numerical_state": left == right,
                    "entries": float.fromhex(left["entries"]),
                    "positive_energy_bin_entries": sum(bin_values[2:]),
                    "differences": differences(left, right) if left != right else {},
                })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--target", choices=("jets", "met"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--booking-probe", action="store_true",
                        help="Check booking scopes only; empty histograms do not validate physics filling")
    parser.add_argument("--expected-removals", choices=("manifest", "none"), default="manifest",
                        help="Use 'none' only for a comparator control, not a cleanup validation")
    args = parser.parse_args()
    import ROOT
    ROOT.gROOT.SetBatch(True)
    ROOT.TH1.AddDirectory(False)
    report = {"target": args.target, "created_utc": datetime.now(timezone.utc).isoformat(),
              "expected_removed_paths": REMOVALS[args.target] if args.expected_removals == "manifest" else [],
              "expected_removal_mode": args.expected_removals, "status": "INPUT_ERROR"}
    rc = 2
    try:
        reference = read_file(args.reference, ROOT)
        audit = reference_audit(reference, args.target)
        report["reference_audit"] = audit
        report["reference_inventory"] = {k: v for k, v in reference.items() if k != "audit"}
        report["reference_object_count"] = len(reference["objects"])
        missing = audit["missing_removal_targets"]
        if args.target == "jets":
            useful = all(pair["equal_numerical_state"] and pair["entries"] > 0
                         and pair["positive_energy_bin_entries"] > 0
                         for pair in audit["muon_duplicate_pairs"])
            useful = useful and len(audit["muon_duplicate_pairs"]) >= 2
        else:
            useful = True
        if args.booking_probe:
            useful = True
            report["test_purpose"] = "Booking scopes only; one EmptySource event; no physics-filling claim"
        if args.candidate:
            candidate = read_file(args.candidate, ROOT)
            if reference["format"] != candidate["format"]:
                raise InputError("Input formats differ")
            report["candidate_inventory"] = {k: v for k, v in candidate.items() if k != "audit"}
            left, right = reference["objects"], candidate["objects"]
            removed = sorted(set(left) - set(right))
            added = sorted(set(right) - set(left))
            changed = sorted(key for key in set(left) & set(right)
                             if left[key]["sha256"] != right[key]["sha256"])
            expected = sorted(key for key, rec in left.items() if rec["path"] in report["expected_removed_paths"])
            report.update(removed_keys=removed, added_keys=added, changed_retained_keys=changed,
                          retained_equal_count=len(set(left) & set(right)) - len(changed),
                          candidate_object_count=len(right), expected_removed_keys=expected)
            ok = removed == expected and not added and not changed
        else:
            ok = True
            report["mode"] = "reference audit only; no cleanup comparison performed"
        required_missing = missing + (audit["missing_preserved_monitors"] if args.target == "jets" else [])
        report["status"] = "PASS" if ok and not required_missing and useful else "UNVERIFIED" if ok else "FAIL"
        rc = 0 if report["status"] == "PASS" else 3 if report["status"] == "UNVERIFIED" else 1
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    displayed = {k: v for k, v in report.items() if not k.endswith("inventory") and k != "reference_audit"}
    if len(displayed.get("changed_retained_keys", [])) > 12:
        displayed["changed_retained_count"] = len(displayed["changed_retained_keys"])
        displayed["changed_retained_keys"] = displayed["changed_retained_keys"][:12]
        displayed["full_report"] = str(args.output.resolve())
    print(json.dumps(displayed, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
