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
    parser.add_argument("--output", type=str, required=True, help="The output file and its path")
    parser.add_argument("--mc_dataset", type=str, help="The MC dataset quer query for calculating the pileup MC file")
    parser.add_argument("--save_mc", action="store_true", help="Save the pileup MC file")
    parser.add_argument("--rdf_filter", type=str, default="", help="RDataFrame filter for the MC pileup calculation, eg. a trigger path")
    parser.add_argument("--numPileupBins", type=int, default=0, help="Number of bins for the MC histogram. Defaults to the binning of the data histogram, ie. what pileupCalc.py produced.")
    parser.add_argument("--maxPileupBin", type=int, default=0, help="Upper edge of the MC histogram. Defaults to the binning of the data histogram.")
    parser.add_argument("--threads", type=int, default=16, help="Number of threads for the MC RDataFrame loop (default: 16)")
    parser.add_argument("--mc_branch", type=str, default="Pileup_nTrueInt", help="MC branch to histogram (default: Pileup_nTrueInt). Use Pileup_nPU together with a data histogram made with --calcMode observed when the sample was digitised at a single fixed pileup, so Pileup_nTrueInt has no spread to reweight.")
    parser.add_argument("--file_prefix", type=str, default="root://cms-xrd-global.cern.ch/", help="Prefix prepended to the DAS logical file names (default: root://cms-xrd-global.cern.ch/). On lxplus, files hosted at T2_CH_CERN read far faster with the prefix /eos/cms")

    args = parser.parse_args()

    if args.calculate_mc and not args.mc_dataset:
        parser.error("--calculate_mc requires --mc_dataset")

    return args

def calculate_mc_pileup(dataset: str, output: str, save_output: bool = False, rdf_filter: str = "",
                        num_bins: int = 100, max_bin: int = 100,
                        file_prefix: str = "root://cms-xrd-global.cern.ch/",
                        branch: str = "Pileup_nTrueInt"):
    output = output.replace(".root", "") + "_mc_reference.root"
    file_dir = os.path.join(os.path.dirname(os.path.abspath(output)) or ".", "pileup_mc_files")

    # Find the dataset files
    print(f"Finding the files for dataset {dataset}")
    call = (f"python3 {os.environ.get('LUMIENV', '.')}/CommonTools/find_dataset.py "
            f"--dataset_query {dataset} --output_dir {file_dir} --combine")
    print("-----------------------------------")
    print(call)
    os.system(call)
    print()

    chain = ROOT.TChain("Events")
    prefix = file_prefix
    combined = os.path.join(file_dir, "combined.txt")
    n_files = 0
    with open(combined, "r") as f:
        for line in f:
            if line.strip():
                chain.Add(prefix + line.strip())
                n_files += 1
    if n_files == 0:
        raise RuntimeError(f"No files found for {dataset}, check {combined}")
    print(f"Added {n_files} file(s) to the chain")

    rdf = ROOT.RDataFrame(chain)
    ROOT.RDF.Experimental.AddProgressBar(rdf)

    if rdf_filter:
        rdf = rdf.Filter(rdf_filter)

    pu_hist = rdf.Histo1D((branch, "pileup_mc", num_bins, 0, max_bin),
                          branch, "genWeight").GetValue()

    if save_output:
        f = ROOT.TFile(output, "RECREATE")
        pu_hist.Write()
        f.Close()
        print(f"MC reference histogram written to {output}")

    return pu_hist

def calculate_data_pileup(file: str, output_dir: str = "pileup_data_files"):
    raise NotImplementedError(
        "Calculating the data pileup histogram here is not implemented. "
        "Run Pileup/produce_pileupHist.py and pass the result with --pileup_dt."
    )

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
        # Match the MC binning to whatever pileupCalc.py produced, unless overridden
        num_bins = args.numPileupBins if args.numPileupBins else dt_hist.GetNbinsX()
        max_bin = args.maxPileupBin if args.maxPileupBin else int(dt_hist.GetXaxis().GetXmax())
        print(f"Filling the MC histogram with {num_bins} bins over [0, {max_bin}]")
        ROOT.EnableImplicitMT(args.threads)
        mc_hist = calculate_mc_pileup(args.mc_dataset, args.output, args.save_mc,
                                      rdf_filter=args.rdf_filter,
                                      num_bins=num_bins, max_bin=max_bin,
                                      file_prefix=args.file_prefix,
                                      branch=args.mc_branch)
    else:
        mc_file = ROOT.TFile(args.pileup_mc, "READ")
        mc_hist = mc_file.Get(args.mc_branch)
        mc_hist.SetName("pileup_mc")
        mc_hist.SetDirectory(0)
        mc_file.Close()

    if (mc_hist.GetNbinsX() != dt_hist.GetNbinsX()
            or mc_hist.GetXaxis().GetXmax() != dt_hist.GetXaxis().GetXmax()):
        raise RuntimeError(
            f"Binning mismatch: data has {dt_hist.GetNbinsX()} bins over "
            f"[0, {dt_hist.GetXaxis().GetXmax()}], MC has {mc_hist.GetNbinsX()} bins over "
            f"[0, {mc_hist.GetXaxis().GetXmax()}]. Rebin the MC histogram, or rerun "
            f"produce_pileupHist.py with matching --numPileupBins/--maxPileupBin."
        )

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
    path = os.path.dirname(args.output)
    if path and not os.path.exists(path):
        os.makedirs(path)

    if not args.output.endswith(".root"):
        args.output += ".root"

    f = ROOT.TFile(f"{args.output}", "RECREATE")
    pu_hist.Write()
    dt_hist.Write()
    mc_hist.Write()
    f.Close()


