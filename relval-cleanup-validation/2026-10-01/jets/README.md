This report records the completed jets RelVal cleanup validation. The acceptance comparison uses 100 TTbar events from workflow 18434.0, scenario 2026, without additional pileup. It is a technical test, and central CI and broader physics validation remain separate.

Release: `CMSSW_20_1_X_2026-09-30-2300`. Base SHA: `08c21e8297763e2aa5ad08c44a507e607e91c84b`. Architecture: `el9_amd64_gcc14`. Era: `Run3_2026`. Geometry: `DB:Extended`. Conditions: `auto:phase1_2026_realistic`, resolved to `160X_mcRun3_2026_realistic_v6`.

The official four-step reference (GenSim, Digi, RecoNano, HARVESTNano) completed successfully. ALCA was skipped. Both acceptance RECO/harvesting replays reuse the same step2.root and run sequentially in one HTCondor allocation on `b9g42p2007.cern.ch`, with one thread and one stream. Both cfgs append the same two thread/stream settings to the original matrix cfgs. The reference and candidate cfgs and their expanded forms are byte identical. No reconstruction or selection code was changed.

Input SHA256: `ae7c230008938a06431c5dc6dccd254a26216d18fe2429dcd28b6bcd7f5b494f`. Exactly 100 events were read by each RECO replay. All four acceptance cmsRun exits are 0 and their framework reports contain no FrameworkError.

| Output | Reference MEs | Candidate MEs | Removed | Retained equal | Added | Retained changed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dqmio | 6930 | 6926 | 4 | 6926 | 0 | 0 |
| harvested | 9029 | 9025 | 4 | 9025 | 0 | 0 |

The comparator preserves run/lumi scopes and normalizes only the DQMData/Run/Run summary storage prefix. It checks every JetMET and HLT/JetMET ME, including Offline DQM controls. It compares histogram class, names/titles, axes, binning, labels, every cell including underflow/overflow, errors, entries, statistics, accumulators and profile population/error state. The full inventories and digests are in the compressed comparison reports. Unrelated subsystem directories are excluded from this targeted comparison.

The booking-only control uses one EmptySource event to test the exact selected folders, other collections, MiniAOD and HLT. Its retained MEs are unchanged; it does not establish physics filling. The event reference separately establishes that the selected removal targets are present and populated.

The following paths were removed:

- `JetMET/JetValidation/ak4CaloJets/n60`
- `JetMET/JetValidation/ak4CaloJets/n90`
- `JetMET/JetValidation/ak4PFJets/chargedMuEnergy`
- `JetMET/JetValidation/ak4PFJets/chargedMuEnergyFraction`

Reference entries and flows:

| Monitor | Entries | Underflow | Overflow |
| --- | ---: | ---: | ---: |
| `JetMET/JetValidation/ak4CaloJets/n60` | 272 | 0 | 0 |
| `JetMET/JetValidation/ak4CaloJets/n90` | 272 | 0 | 1 |
| `JetMET/JetValidation/ak4PFJets/chargedMuEnergy` | 311 | 0 | 0 |
| `JetMET/JetValidation/ak4PFJets/chargedMuEnergyFraction` | 311 | 0 | 4 |

The chargedMu/muon pairs have identical numerical histogram state, including flow bins, and contain positive-energy entries. The muon monitors, all nine selected regional multiplicity MEs, inclusive multiplicities and HadronFlavor/PartonFlavor are retained.

Earlier full RECO replays with four threads completed cmsRun but did not pass strict retained-ME equality. These results are preserved:

| Attempt | Reference host | Candidate host | Removed | Added | Retained changed |
| --- | --- | --- | ---: | ---: | ---: |
| candidate-attempt01 | b9p29p8354.cern.ch | b9p13p8814.cern.ch | 4 | 0 | 3098 |
| candidate | b9p29p8354.cern.ch | b9p29p8354.cern.ch | 4 | 0 | 422 |

An additional unmodified four-thread control replay on `b9p29p8354.cern.ch`, with the same source, RAW SHA256, CPU model and byte-identical expanded cfg as the original Jets reference, also changed 379 retained MEs. It removed and added none, and all retained entries were equal. Its cmsRun exit was 0; the strict numerical comparison was FAIL. The control report is stored with the Jets artifacts. This establishes that the observed four-thread reproduction issue also occurs without either cleanup patch.

The strict acceptance result is the serial pair above. Four-thread reproducibility is recorded as a limitation, rather than counting these earlier comparisons as passing. [VirtualJetProducer.cc](https://github.com/cms-sw/cmssw/blob/08c21e8297763e2aa5ad08c44a507e607e91c84b/RecoJets/JetProducers/plugins/VirtualJetProducer.cc#L273) documents FastJet ghost-area generation using a global random-number sequence; its role in the observed differences is a diagnostic inference.

Build, package runtests, dependency check, code-checks, code-format and diff checks all passed. The relevant plotting test ran; it was not skipped. No dependencies or source changed after the successful candidate build. The broader limited matrix was not run.

RECO/harvesting error-category and message comparisons add no new error messages. Existing reference diagnostics include the unavailable ak4PFJetsPuppiCorrected input in an unrelated Offline PF DQM analyzer and baseline harvesting diagnostics. These do not prevent the selected RelVal testers from running and filling their monitors. See validation-summary.json for exact categories and counts.

The PR contains only its tester .cc change. This validation branch contains the reports, cfgs and comparator separately. ROOT outputs and complete expanded cfgs remain in the CERN EOS validation area, without publishing access parameters.
