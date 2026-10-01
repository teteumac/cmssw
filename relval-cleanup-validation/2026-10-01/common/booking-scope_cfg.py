"""Booking-only control of exact folders; one EmptySource event, no physics input."""
import FWCore.ParameterSet.Config as cms
from Validation.RecoJets.JetValidation_cfi import (
    JetAnalyzerAk4Calo, JetAnalyzerAk4PF, JetAnalyzerAk4PFCHS,
    JetAnalyzerAk4PFCHSMiniAOD, JetAnalyzerAk4PFPUPPIMiniAOD,
    JetAnalyzerAk8PFPUPPIMiniAOD,
)
from Validation.RecoMET.METValidation_cfi import metAnalyzer

process = cms.Process("BOOKINGSCOPE")
process.add_(cms.Service("DQMStore"))
process.source = cms.Source("EmptySource")
process.maxEvents = cms.untracked.PSet(input=cms.untracked.int32(1))
process.options = cms.untracked.PSet(numberOfThreads=cms.untracked.uint32(4),
                                     numberOfStreams=cms.untracked.uint32(1))
process.caloOffline = JetAnalyzerAk4Calo.clone(JetCorrections=cms.InputTag(""))
process.caloHLT = process.caloOffline.clone(isHLT=cms.untracked.bool(True))
process.pfOffline = JetAnalyzerAk4PF.clone(JetCorrections=cms.InputTag(""))
process.pfHLT = process.pfOffline.clone(isHLT=cms.untracked.bool(True))
process.pfCHS = JetAnalyzerAk4PFCHS.clone(JetCorrections=cms.InputTag(""))
process.patCHS = JetAnalyzerAk4PFCHSMiniAOD.clone()
process.patPuppi = JetAnalyzerAk4PFPUPPIMiniAOD.clone()
process.patAK8Puppi = JetAnalyzerAk8PFPUPPIMiniAOD.clone()
process.metDefault = metAnalyzer.clone()
process.metHLT = metAnalyzer.clone(runDir=cms.untracked.string("HLT/JetMET/METValidation/"))
process.metAlternate = metAnalyzer.clone(runDir=cms.untracked.string("JetMET/METValidation/alternate/"))
process.test = cms.Path(process.caloOffline + process.caloHLT + process.pfOffline + process.pfHLT
                        + process.pfCHS + process.patCHS + process.patPuppi + process.patAK8Puppi
                        + process.metDefault + process.metHLT + process.metAlternate)
process.output = cms.OutputModule("DQMRootOutputModule",
                                  fileName=cms.untracked.string("booking-scope.root"))
process.save = cms.EndPath(process.output)
