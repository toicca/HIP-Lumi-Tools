import json
import os
import sys
import numpy as np
import argparse
import subprocess

def parse_arguments():
    parser = argparse.ArgumentParser(description="Produce a ROOT histogram with pileup information")
    parser.add_argument("--year", required=True, choices=["2016", "2017", "2018", "2022", "2023", "2024", "2025", "2026"], type=str, help="Year to process. Used to determine the pileup latest file if not provided and the output file name")
    parser.add_argument("--lumijson", required=True, type=str, help="Luminosity block JSON file such as GoldenJSON or DCSOnly")
    parser.add_argument("--trigger", type=str, help="Trigger that's used to get the pileup information")
    parser.add_argument("--pileup-latest", type=str, default="", help="Pileup latest file. Check Data/PileupJSONS.json for the latest pileup files for each year.")
    parser.add_argument("--minBiasXsec", type=int, default=69200, help="Minimum bias cross section")
    parser.add_argument("--maxPileupBin", type=int, default=100, help="Upper edge of the pileup histogram (default: 100)")
    parser.add_argument("--numPileupBins", type=int, default=100, help="Number of bins in the pileup histogram (default: 100). Use a larger value for low pileup data, where 1.0 wide bins leave only a handful of populated bins.")
    parser.add_argument("--tag", type=str, default="", help="Extra tag for the output file name, eg. the pileup band a lumijson selects")
    parser.add_argument("--calcMode", type=str, choices=["true", "observed"], default="true", help="pileupCalc mode. 'true' gives the distribution of the true pileup, to reweight Pileup_nTrueInt. 'observed' Poisson smears it, to reweight Pileup_nPU, which is what a sample digitised at a single fixed pileup needs.")
    parser.add_argument("--vary-minBiasXsec", type=int, default=0, help="Vary the minimum bias cross section by this amount (ub)") # 3200 for run 2
    parser.add_argument("--output-path", type=str, default="./", help="Output path")
    parser.add_argument("--ignore-normtag", action="store_true", help="Ignore the normtag in brilcalc call")
    parser.add_argument("--normtag", type=str, choices=["BRIL", "PHYSICS",], default="BRIL", help="Normtag to use in brilcalc call (default: BRIL)")

    args = parser.parse_args()

    return args

BRILCALC = "singularity -s exec --env PYTHONPATH=/home/bril/.local/lib/python3.10/site-packages /cvmfs/unpacked.cern.ch/gitlab-registry.cern.ch/cms-cloud/brilws-docker:latest brilcalc"

def create_histogram(
    year: str,
    lumijson: str,
    output_path: str = "./",
    trigger: str = None,
    pileup_latest: str = "pileup_latest.txt",
    minBiasXsec: int = 69200,
    maxPileupBin: int = 100,
    numPileupBins: int = 100,
    tag: str = "",
    normtag: str = "BRIL",
    ignore_normtag: bool = False,
    calcMode: str = "true"
    ):
    if output_path[-1] != "/":
        output_path += "/"
    name = f'pileup_{year}{"_"+tag if tag else ""}{"_"+trigger if trigger else ""}_{minBiasXsec}ub'
    if numPileupBins != maxPileupBin:
        name += f"_{numPileupBins}bins"
    if maxPileupBin != 100:
        name += f"_max{maxPileupBin}"
    if calcMode != "true":
        name += f"_{calcMode}"
    output = f"{output_path}{name}.root"
    lumi_csv = f"{output_path}.brilcalc_{name}.csv"

    # The brilcalc CSV is only consumed by pileupReCalc_HLTpaths.py, so it is only
    # needed for the per-trigger case. Without a trigger pileupCalc.py works straight
    # off the lumi JSON and the pileup JSON.
    if trigger:
        print("Calling brilcalc to get the luminosity")
        call = f"{BRILCALC} lumi --byls -i {lumijson} -o {lumi_csv} --hltpath {trigger}_v*"
        if not ignore_normtag:
            call += f" --normtag /cvmfs/cms-bril.cern.ch/cms-lumi-pog/Normtags/normtag_{normtag}.json"
        print("-----------------------------------")
        print(call)
        os.system(call)
        print()

    if trigger:
        call = f'pileupReCalc_HLTpaths.py -i {lumi_csv} --inputLumiJSON {pileup_latest} -o {output_path}temp_pileup.txt --runperiod Run2'
        print("Calling pileupReCalc_HLTpaths.py")
        print("-----------------------------------")
        print(call)
        os.system(call)
        print()

    call = f'pileupCalc.py -i {lumijson} --inputLumiJSON {output_path+"temp_pileup.txt" if trigger else pileup_latest} --calcMode {calcMode} --minBiasXsec {minBiasXsec} --maxPileupBin {maxPileupBin} --numPileupBins {numPileupBins} {output}'
    print("Calling pileupCalc.py")
    print("-----------------------------------")
    print(call)
    os.system(call)
    print()

    if trigger:
        os.system(f"rm -f {lumi_csv}")
        os.system(f"rm -f {output_path}temp_pileup.txt")
    
    print(f"Output file: {output}")

def ensure_singularity_bindpath():
    """
    The brilcalc image needs /cvmfs, /eos and /afs bound. activate_environment.sh
    does this by sourcing brilws-env; do it here too so the script also works when
    it has not been sourced, instead of failing with a missing shared library.
    """
    if os.environ.get("SINGULARITY_BINDPATH"):
        return
    out = subprocess.run(
        'source /cvmfs/cms-bril.cern.ch/cms-lumi-pog/brilws-docker/brilws-env >/dev/null 2>&1; echo "$SINGULARITY_BINDPATH"',
        shell=True, executable="/bin/bash", capture_output=True, text=True,
    )
    bindpath = out.stdout.strip()
    if bindpath:
        os.environ["SINGULARITY_BINDPATH"] = bindpath
        os.environ["APPTAINER_BINDPATH"] = bindpath


if __name__ == "__main__":
    args = parse_arguments()
    ensure_singularity_bindpath()

    if not args.pileup_latest:
        with open(os.environ["LUMIENV"]+"/Data/PileupJSONS.json") as f:
            pileup_latest = json.load(f)
        if args.year not in pileup_latest:
            sys.exit(f"No pileup JSON known for {args.year}. Add it to Data/PileupJSONS.json, "
                     f"pass --pileup-latest, or produce one with Pileup/produce_pileupJSON.py.")
        args.pileup_latest = os.path.expandvars(pileup_latest[args.year])

    for xsec in [args.minBiasXsec] + ([args.minBiasXsec + args.vary_minBiasXsec,
                                       args.minBiasXsec - args.vary_minBiasXsec]
                                      if args.vary_minBiasXsec != 0 else []):
        create_histogram(args.year, args.lumijson, args.output_path, args.trigger,
                         args.pileup_latest, xsec, args.maxPileupBin, args.numPileupBins,
                         args.tag, args.normtag, args.ignore_normtag, args.calcMode)