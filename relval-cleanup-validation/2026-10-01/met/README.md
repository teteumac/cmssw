This report records the completed met RelVal cleanup validation. The acceptance comparison uses 100 TTbar events from workflow 18434.0, scenario 2026, without additional pileup. It is a technical test, and central CI and broader physics validation remain separate.

Release: `CMSSW_20_1_X_2026-09-30-2300`. Base SHA: `08c21e8297763e2aa5ad08c44a507e607e91c84b`. Architecture: `el9_amd64_gcc14`. Era: `Run3_2026`. Geometry: `DB:Extended`. Conditions: `auto:phase1_2026_realistic`, resolved to `160X_mcRun3_2026_realistic_v6`.

The official four-step reference (GenSim, Digi, RecoNano, HARVESTNano) completed successfully. ALCA was skipped. Both acceptance RECO/harvesting replays reuse the same step2.root and run sequentially in one HTCondor allocation on `b9g42p1018.cern.ch`, with one thread and one stream. Both cfgs append the same two thread/stream settings to the original matrix cfgs. The reference and candidate cfgs and their expanded forms are byte identical. No reconstruction or selection code was changed.

Input SHA256: `4929be0ade195675bfafe0b038e0c49321534f23579985eacc82a47818aaf166`. Exactly 100 events were read by each RECO replay. All four acceptance cmsRun exits are 0 and their framework reports contain no FrameworkError.

| Output | Reference MEs | Candidate MEs | Removed | Retained equal | Added | Retained changed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dqmio | 6930 | 6928 | 2 | 6928 | 0 | 0 |
| harvested | 9029 | 9027 | 2 | 9027 | 0 | 0 |

The comparator preserves run/lumi scopes and normalizes only the DQMData/Run/Run summary storage prefix. It checks every JetMET and HLT/JetMET ME, including Offline DQM controls. It compares histogram class, names/titles, axes, binning, labels, every cell including underflow/overflow, errors, entries, statistics, accumulators and profile population/error state. The full inventories and digests are in the compressed comparison reports. Unrelated subsystem directories are excluded from this targeted comparison.

The booking-only control uses one EmptySource event to test the exact selected folders, other collections, MiniAOD and HLT. Its retained MEs are unchanged; it does not establish physics filling. The event reference separately establishes that the selected removal targets are present and populated.

The following paths were removed:

- `JetMET/METValidation/caloMet/CaloSETInmHF`
- `JetMET/METValidation/caloMet/CaloSETInpHF`

Reference entries and flows:

| Monitor | Entries | Underflow | Overflow |
| --- | ---: | ---: | ---: |
| `JetMET/METValidation/caloMet/CaloSETInmHF` | 100 | 0 | 0 |
| `JetMET/METValidation/caloMet/CaloSETInpHF` | 100 | 0 | 0 |

The two HF SET monitors are populated in this reference. Their removal is an inventory monitoring-content reduction, and is not justified as structurally missing Fill or as always blank. Other CaloMET/HF monitoring is retained.

Earlier full RECO replays with four threads completed cmsRun but did not pass strict retained-ME equality. These results are preserved:

| Attempt | Reference host | Candidate host | Removed | Added | Retained changed |
| --- | --- | --- | ---: | ---: | ---: |
| candidate | b9p19p2832.cern.ch | b9p19p2832.cern.ch | 2 | 0 | 257 |

An additional unmodified four-thread control replay on `b9p29p8354.cern.ch`, with the same source, RAW SHA256, CPU model and byte-identical expanded cfg as the original Jets reference, also changed 379 retained MEs. It removed and added none, and all retained entries were equal. Its cmsRun exit was 0; the strict numerical comparison was FAIL. The control report is stored with the Jets artifacts. This establishes that the observed four-thread reproduction issue also occurs without either cleanup patch.

The strict acceptance result is the serial pair above. Four-thread reproducibility is recorded as a limitation, rather than counting these earlier comparisons as passing. [VirtualJetProducer.cc](https://github.com/cms-sw/cmssw/blob/08c21e8297763e2aa5ad08c44a507e607e91c84b/RecoJets/JetProducers/plugins/VirtualJetProducer.cc#L273) documents FastJet ghost-area generation using a global random-number sequence; its role in the observed differences is a diagnostic inference.

Build, package runtests, dependency check, code-checks, code-format and diff checks all passed. The relevant plotting test ran; it was not skipped. No dependencies or source changed after the successful candidate build. The broader limited matrix was not run.

RECO/harvesting error-category and message comparisons add no new error messages. Existing reference diagnostics include the unavailable ak4PFJetsPuppiCorrected input in an unrelated Offline PF DQM analyzer and baseline harvesting diagnostics. These do not prevent the selected RelVal testers from running and filling their monitors. See validation-summary.json for exact categories and counts.

The PR contains only its tester .cc change. This validation branch contains the reports, cfgs and comparator separately. ROOT outputs and complete expanded cfgs remain in the CERN EOS validation area, without publishing access parameters.
