#!/usr/bin/env python3
"""
Rebin a pileup histogram by an integer factor.

Filling the MC Pileup_nTrueInt histogram means reading the whole NanoAOD sample,
so it is done once at the finest binning needed and coarser versions are made
here instead of by a second pass over the files. Only exact divisors are allowed,
so no bin boundary moves.

Usage:
    python3 Pileup/rebin_pileupHist.py in.root out.root --rebin 10
"""

import argparse
import os
import sys

import ROOT

ROOT.gROOT.SetBatch(True)


def truncate(h, xmax):
    """Return a copy of h with the axis cut at xmax, folding the rest into the overflow."""
    width = h.GetXaxis().GetBinWidth(1)
    nbins = xmax / width
    if abs(nbins - round(nbins)) > 1e-6:
        sys.exit(f"--xmax {xmax} does not fall on a bin edge of {h.GetName()} "
                 f"(bin width {width:g})")
    nbins = int(round(nbins))
    out = ROOT.TH1D(h.GetName(), h.GetTitle(), nbins, h.GetXaxis().GetXmin(), xmax)
    out.SetDirectory(0)
    out.Sumw2()
    for i in range(0, h.GetNbinsX() + 2):
        target = min(i, nbins + 1)
        out.SetBinContent(target, out.GetBinContent(target) + h.GetBinContent(i))
        out.SetBinError(target, (out.GetBinError(target) ** 2 + h.GetBinError(i) ** 2) ** 0.5)
    out.SetEntries(h.GetEntries())
    return out


def parse_arguments():
    parser = argparse.ArgumentParser(description="Rebin a pileup histogram by an integer factor")
    parser.add_argument("input", help="Input ROOT file")
    parser.add_argument("output", help="Output ROOT file")
    parser.add_argument("--rebin", type=int, default=1, help="Rebinning factor, must divide the number of bins (default: 1, no rebinning)")
    parser.add_argument("--hist", type=str, default="", help="Histogram to rebin (default: every TH1 in the file)")
    parser.add_argument("--xmax", type=float, default=0, help="Also truncate the axis to [0, xmax]. Must fall on a bin edge of the rebinned histogram, so no bin boundary moves. Overflow is folded into the last bin.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    fin = ROOT.TFile(args.input, "READ")
    if not fin or fin.IsZombie():
        sys.exit(f"Cannot open {args.input}")

    names = [args.hist] if args.hist else [k.GetName() for k in fin.GetListOfKeys()]
    hists = []
    for name in names:
        h = fin.Get(name)
        if not h or not h.InheritsFrom("TH1"):
            print(f"Skipping {name}, not a TH1")
            continue
        if h.GetNbinsX() % args.rebin != 0:
            sys.exit(f"{name} has {h.GetNbinsX()} bins, which --rebin {args.rebin} does not divide")
        h.SetDirectory(0)
        if args.rebin > 1:
            h.Rebin(args.rebin)
        if args.xmax:
            h = truncate(h, args.xmax)
        hists.append(h)
    fin.Close()

    if not hists:
        sys.exit(f"Nothing to rebin in {args.input}")

    path = os.path.dirname(args.output)
    if path and not os.path.exists(path):
        os.makedirs(path)

    fout = ROOT.TFile(args.output, "RECREATE")
    for h in hists:
        h.Write()
        print(f"{h.GetName()}: {h.GetNbinsX()} bins over "
              f"[{h.GetXaxis().GetXmin():g}, {h.GetXaxis().GetXmax():g}], "
              f"integral {h.Integral(0, h.GetNbinsX() + 1):.6g}")
    fout.Close()
    print(f"Wrote {args.output}")
