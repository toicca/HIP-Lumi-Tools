# HIP Lumi tools

Tools to get luminosities, pileup profiles and prescales that can be passed to other software.

## Setup

All scripts here are intended to be run on Lxplus with CMSSW and brilcalc. The initial setup should be

```
cmsrel CMSSW_14_0_9
cd CMSSW_14_0_9/src
cmsenv
export PATH=$HOME/.local/bin:/cvmfs/cms-bril.cern.ch/brilconda3/bin:$PATH
pip install --user --upgrade brilws
scram b -j
cd -
```

For later use one can simply run 

```
cd CMSSW_14_0_9/src
cmsenv
cd -
```