#!/usr/bin/env bash
cmsrel CMSSW_15_0_2
cd CMSSW_15_0_2/src
cmsenv
export PATH=$HOME/.local/bin:/cvmfs/cms-bril.cern.ch/brilconda39/bin:$PATH
pip install --user --upgrade brilws
scram b -j
cd -