import json
import os
import sys
import numpy as np
import argparse
import subprocess

def parse_arguments():
    parser = argparse.ArgumentParser(description="Produce a ROOT histogram with pileup information")
    parser.add_argument("--year", required=True, choices=["2016", "2017", "2018", "2022", "2023", "2024"], type=str, help="Era")
    parser.add_argument("--lumijson", type=str, help="Luminosity block JSON file such as GoldenJSON or DCSOnly")
    parser.add_argument("--trigger", type=str, help="Trigger to that's used to get the pileup information")
    parser.add_argument("--pileup_latest", type=str, default="", help="Pileup latest file")
    parser.add_argument("--minBiasXsec", type=int, default=69200, help="Minimum bias cross section")
    parser.add_argument("--vary_minBiasXsec", type=int, default=0, help="Vary the minimum bias cross section by this amount (ub)") # 3200 for run 2
    parser.add_argument("--output_path", type=str, default="./", help="Output path")

    args = parser.parse_args()

    return args

def create_histogram(year: str, lumijson: str, output_path: str = "./", trigger: str = None, pileup_latest: str = "pileup_latest.txt", minBiasXsec: int = 69200):
    if output_path[-1] != "/":
        output_path += "/"
    output = f'{output_path}pileup_{year}{"_"+trigger if trigger else ""}_{minBiasXsec}ub.root'

    print("Calling brilcalc to get the luminosity")
    call = f"brilcalc lumi --byls --normtag /cvmfs/cms-bril.cern.ch/cms-lumi-pog/Normtags/normtag_PHYSICS.json -i {lumijson} -o output.csv"
    if trigger:
        call += f" --hltpath {trigger}_v*"
    print("-----------------------------------")
    print(call)
    os.system(call)
    print()

    if trigger:
        call = f'pileupReCalc_HLTpaths.py -i output.csv --inputLumiJSON {pileup_latest} -o temp_pileup.txt --runperiod Run2'
        print("Calling pileupReCalc_HLTpaths.py")
        print("-----------------------------------")
        print(call)
        os.system(call)
        print()

    call = f'pileupCalc.py -i {lumijson} --inputLumiJSON {"temp_pileup.txt" if trigger else pileup_latest} --calcMode true --minBiasXsec {minBiasXsec} --maxPileupBin 100 --numPileupBins 100 {output}'
    print("Calling pileupCalc.py")
    print("-----------------------------------")
    print(call)
    os.system(call)
    print()

    os.system("rm output.csv")
    if trigger:
        os.system("rm temp_pileup.txt")
    
    print(f"Output file: {output}")

if __name__ == "__main__":
    args = parse_arguments()
    if not args.pileup_latest:
        with open(os.environ["LUMIENV"]+"/Data/PileupJSONS.json") as f:
            pileup_latest = json.load(f)
            args.pileup_latest = pileup_latest[args.year]
    create_histogram(args.year, args.lumijson, args.output_path, args.trigger, args.pileup_latest, args.minBiasXsec)

    if args.vary_minBiasXsec != 0:
        create_histogram(args.year, args.lumijson, args.output_path, args.trigger, args.pileup_latest, args.minBiasXsec + args.vary_minBiasXsec)
        create_histogram(args.year, args.lumijson, args.output_path, args.trigger, args.pileup_latest, args.minBiasXsec - args.vary_minBiasXsec)