#!/usr/bin/env bash
cd CMSSW_15_0_2/src
cmsenv
cd -
export LUMIENV=$PWD
source /cvmfs/cms-bril.cern.ch/cms-lumi-pog/brilws-docker/brilws-env