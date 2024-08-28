#!/usr/bin/env bash
cmsrel CMSSW_14_0_9
cd CMSSW_14_0_9/src
cmsenv
export PATH=$HOME/.local/bin:/cvmfs/cms-bril.cern.ch/brilconda3/bin:$PATH
pip install --user --upgrade brilws
scram b -j
cd -