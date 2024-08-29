import ROOT
import argparse
import os
import subprocess

def parse_arguments():
    parser = argparse.ArgumentParser(description="Produce a pileup weights histogram file")
    dt_group = parser.add_mutually_exclusive_group(required=True)
    dt_group.add_argument("--pileup_dt", type=str, help="The pileup data file")
    dt_group.add_argument("--calculate_pileup", action="store_true", help="Calculate the pileup data file")
    mc_group = parser.add_mutually_exclusive_group(required=True)
    mc_group.add_argument("--pileup_mc", type=str, help="The pileup MC file")
    mc_group.add_argument("--calculate_mc", action="store_true", help="Calculate the pileup MC file")
    parser.add_argument("--output", type=str, required=True, help="The output directory")
    parser.add_argument("--mc_dataset", type=str, help="The MC dataset for calculating the pileup MC file")
    parser.add_argument("--save_mc", action="store_true", help="Save the pileup MC file")
    parser.add_argument("--rdf_filter", type=str, default="", help="RDataFrame filter for the MC pileup calculation, eg. a trigger path")

    args = parser.parse_args()

    return args

def calculate_mc_pileup(dataset: str, save_output: bool = False, rdf_filter: str = "", output_dir: str = "pileup_mc_files"):
    # Find the dataset files
    print(f"Finding the files for dataset {dataset}")
    call = f"python3 CommonTools/find_dataset.py --dataset_query {dataset} --output pileup_mc_files --combine"
    print("-----------------------------------")
    print(call)
    os.system(call)
    print()

    chain = ROOT.TChain("Events")
    prefix = "root://cms-xrd-global.cern.ch/"
    with open("pileup_mc_files/combined.txt", "r") as f:
        for line in f:
            chain.Add(prefix + line.strip())

    rdf = ROOT.RDataFrame(chain)
    ROOT.RDF.Experimental.AddProgressBar(rdf)

    if rdf_filter:
        rdf = rdf.Filter(rdf_filter)

    pu_hist = rdf.Histo1D(("Pileup_nTrueInt", "pileup_mc", 100, 0, 100), "Pileup_nTrueInt", "genWeight").GetValue()

    if save_output:
        f = ROOT.TFile(f"{output_dir}/pileup_mc.root", "RECREATE")
        pu_hist.Write()
        f.Close()

    return pu_hist

def calculate_data_pileup(file: str, output_dir: str = "pileup_data_files"):
    # something along the lines of produce_pileupHist.py
    pass

if __name__ == "__main__":
    args = parse_arguments()

    if args.calculate_pileup:
        dt_hist = calculate_data_pileup(args.pileup_dt, args.output)
    else:
        dt_file = ROOT.TFile(args.pileup_dt, "READ")
        dt_hist = dt_file.Get("pileup")
        dt_hist.SetName("pileup_data")
        dt_hist.SetDirectory(0)
        dt_file.Close()
    if args.calculate_mc:
        ROOT.EnableImplicitMT(16)
        mc_hist = calculate_mc_pileup(args.mc_dataset, args.save_mc, output_dir=args.output, rdf_filter=args.rdf_filter)
    else:
        mc_file = ROOT.TFile(args.pileup_mc, "READ")
        mc_hist = mc_file.Get("Pileup_nTrueInt")
        mc_hist.SetName("pileup_mc")
        mc_hist.SetDirectory(0)
        mc_file.Close()

    # Scale to maximum 1
    dt_hist.Scale(1.0/dt_hist.GetMaximum())
    mc_hist.Scale(1.0/mc_hist.GetMaximum())

    # Divide the histograms
    pu_hist = dt_hist.Clone()
    pu_hist.SetName("weights")
    pu_hist.Divide(mc_hist)

    # Set bins with large relative error to 1
    for i in range(1, pu_hist.GetNbinsX() + 1):
        if pu_hist.GetBinContent(i) != 0 and pu_hist.GetBinError(i) / pu_hist.GetBinContent(i) > 0.5:
            pu_hist.SetBinContent(i, 1)
            pu_hist.SetBinError(i, 0)

    # Save the histogram
    f = ROOT.TFile(f"{args.output}/pileup_weights.root", "RECREATE")
    pu_hist.Write()
    dt_hist.Write()
    mc_hist.Write()
    f.Close()


