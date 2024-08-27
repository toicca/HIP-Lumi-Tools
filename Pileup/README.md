brilcalc lumi --byls --normtag /cvmfs/cms-bril.cern.ch/cms-lumi-pog/Normtags/normtag_PHYSICS.json -i [your json] --hltpath [your !HLT path] -o output.csv

pileupReCalc_HLTpaths.py -i output.csv --inputLumiJSON pileup_latest.txt -o My_HLT_corrected_PileupJSON.txt --runperiod Run2

pileupReCalc_HLTpaths.py -i Data/output_UL16_postVFP.csv --inputLumiJSON pileup_latest.txt -o PileupJSON_UL16_postVFP.txt --runperiod Run2

pileupCalc.py -i MyAnalysisJSON.txt --inputLumiJSON pileup_latest.txt --calcMode true --minBiasXsec 69200 --maxPileupBin 100 --numPileupBins 100 MyDataPileupHistogram.root