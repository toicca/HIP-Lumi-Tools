#!/usr/bin/env python3
"""
Write pileup weights as a correctionlib (schema v2) JSON file.

The LUM POG publishes the pileup weights as a gzipped correctionlib file, eg.
/cvmfs/cms-griddata.cern.ch/cat/metadata/LUM/Run3-25Prompt-Summer24-NanoAODv15/latest/
puWeights_2025pp_Golden_Summer24_25ns_69200ub.json.gz, a single correction holding a
category over nominal/up/down and one binning node per key. This script produces the
same structure from the ROOT files of produce_pileupWeight.py, with the nominal and the
two minimum bias cross section variations taken from three separate files.

The ratio is recomputed here rather than copied from the `weights` histogram, because
produce_pileupWeight.py scales data and MC to maximum 1 before dividing, while the
published convention is data/MC with both distributions normalised to unit area. Bins
where the MC is empty get weight 1, as in the published file.

Usage:
    python3 Pileup/produce_pileupCorrectionlib.py \\
        --nominal output/2026_lowPU/pileup_weights_2026_lowPU_pu5_75300ub_max20_observed.root \\
        --up      output/2026_lowPU/pileup_weights_2026_lowPU_pu5_78800ub_max20_observed.root \\
        --down    output/2026_lowPU/pileup_weights_2026_lowPU_pu5_71800ub_max20_observed.root \\
        --mc_branch Pileup_nPU --input-name NumInteractions \\
        --name Collisions26_lowPU_pu5 --validate \\
        --output output/2026_lowPU/puWeights_2026_lowPU_pu5_75300ub_observed.json.gz
"""

import argparse
import gzip
import json
import os
import sys

import ROOT

ROOT.gROOT.SetBatch(True)


def parse_arguments():
    parser = argparse.ArgumentParser(description="Write pileup weights as a correctionlib JSON file")
    parser.add_argument("--nominal", required=True, help="Pileup weights file for the nominal minimum bias cross section, or a bare pileupCalc.py histogram together with --pileup_mc")
    parser.add_argument("--up", type=str, default="", help="Same for the upward cross section variation, eg. 78800 ub for a 75300 ub nominal. Omit to write a file with only the nominal key.")
    parser.add_argument("--down", type=str, default="", help="Same for the downward cross section variation, eg. 71800 ub for a 75300 ub nominal")
    parser.add_argument("--pileup_mc", type=str, default="", help="MC reference file. Only needed when the inputs are bare pileupCalc.py histograms, ie. they hold a single `pileup` histogram instead of the `pileup_data`/`pileup_mc` pair that produce_pileupWeight.py writes.")
    parser.add_argument("--mc_branch", type=str, default="Pileup_nTrueInt", help="Histogram name in --pileup_mc (default: Pileup_nTrueInt). Use Pileup_nPU for the observed mode.")
    parser.add_argument("--name", type=str, default="", help="Correction name (default: the output file stem without the puWeights_ prefix)")
    parser.add_argument("--input-name", type=str, default="NumTrueInteractions", help="Name of the pileup input variable (default: NumTrueInteractions). Use NumInteractions for weights made against Pileup_nPU.")
    parser.add_argument("--description", type=str, default="", help="Description stored with the correction")
    parser.add_argument("--version", type=int, default=0, help="Correction version (default: 0)")
    parser.add_argument("--max-rel-error", type=float, default=0.0, help="Set bins whose relative statistical error exceeds this to weight 1, the way produce_pileupWeight.py does (default: 0, ie. no smoothing, which is what the published files do)")
    parser.add_argument("--validate", action="store_true", help="Read the result back with correctionlib and print a few weights. correctionlib is a CMSSW external, so this needs cmsenv.")
    parser.add_argument("--output", required=True, help="Output file. Gzipped when the name ends in .gz, as the published files are.")

    return parser.parse_args()


def read_pair(path, mc_path, mc_branch):
    """Return the (data, MC) histogram pair of one cross section point.

    Accepts both a produce_pileupWeight.py file, which already holds the pair, and a bare
    pileupCalc.py histogram, which needs the MC reference passed separately.
    """
    f = ROOT.TFile(path, "READ")
    if not f or f.IsZombie():
        sys.exit(f"Cannot open {path}")

    names = [k.GetName() for k in f.GetListOfKeys()]
    if "pileup_data" in names and "pileup_mc" in names:
        dt_hist, mc_hist = f.Get("pileup_data"), f.Get("pileup_mc")
    elif "pileup" in names:
        if not mc_path:
            sys.exit(f"{path} holds a bare pileupCalc.py histogram, so --pileup_mc is required")
        dt_hist, mc_hist = f.Get("pileup"), None
    else:
        sys.exit(f"{path} holds none of `pileup_data`/`pileup_mc` or `pileup`, only {names}")
    dt_hist.SetDirectory(0)
    if mc_hist:
        mc_hist.SetDirectory(0)
    f.Close()

    if mc_hist is None:
        mc_file = ROOT.TFile(mc_path, "READ")
        if not mc_file or mc_file.IsZombie():
            sys.exit(f"Cannot open {mc_path}")
        mc_hist = mc_file.Get(mc_branch)
        if not mc_hist:
            sys.exit(f"No histogram {mc_branch} in {mc_path}")
        mc_hist.SetDirectory(0)
        mc_file.Close()

    if (mc_hist.GetNbinsX() != dt_hist.GetNbinsX()
            or mc_hist.GetXaxis().GetXmax() != dt_hist.GetXaxis().GetXmax()):
        sys.exit(
            f"Binning mismatch in {path}: data has {dt_hist.GetNbinsX()} bins over "
            f"[0, {dt_hist.GetXaxis().GetXmax()}], MC has {mc_hist.GetNbinsX()} bins over "
            f"[0, {mc_hist.GetXaxis().GetXmax()}]. Rebin the MC histogram with "
            f"Pileup/rebin_pileupHist.py, or rerun produce_pileupHist.py with matching "
            f"--numPileupBins/--maxPileupBin."
        )

    return dt_hist, mc_hist


def compute_weights(dt_hist, mc_hist, max_rel_error=0.0):
    """Return the per bin data/MC ratio with both distributions normalised to unit area.

    Bins where the MC is empty get weight 1, so that MC events landing outside the data
    profile are left alone instead of being thrown away.
    """
    nbins = dt_hist.GetNbinsX()
    dt_sum = sum(dt_hist.GetBinContent(i) for i in range(1, nbins + 1))
    mc_sum = sum(mc_hist.GetBinContent(i) for i in range(1, nbins + 1))
    if dt_sum <= 0 or mc_sum <= 0:
        sys.exit(f"Empty histogram: data integral {dt_sum:g}, MC integral {mc_sum:g}")

    content = []
    for i in range(1, nbins + 1):
        mc = mc_hist.GetBinContent(i) / mc_sum
        if mc <= 0:
            content.append(1.0)
            continue
        dt = dt_hist.GetBinContent(i) / dt_sum
        weight = dt / mc
        if max_rel_error > 0 and weight != 0:
            # Same guard as produce_pileupWeight.py, propagating both statistical errors
            dt_err = dt_hist.GetBinError(i) / dt_sum
            mc_err = mc_hist.GetBinError(i) / mc_sum
            rel = ((dt_err / dt) ** 2 + (mc_err / mc) ** 2) ** 0.5 if dt > 0 else float("inf")
            if rel > max_rel_error:
                weight = 1.0
        content.append(weight)

    return content


def bin_edges(hist):
    return [float(hist.GetXaxis().GetBinLowEdge(i)) for i in range(1, hist.GetNbinsX() + 2)]


if __name__ == "__main__":
    args = parse_arguments()

    variations = [("nominal", args.nominal)]
    if args.up:
        variations.append(("up", args.up))
    if args.down:
        variations.append(("down", args.down))

    edges = None
    content = []
    for key, path in variations:
        dt_hist, mc_hist = read_pair(path, args.pileup_mc, args.mc_branch)
        if edges is None:
            edges = bin_edges(dt_hist)
        elif bin_edges(dt_hist) != edges:
            sys.exit(f"{path} does not share the binning of {args.nominal}; all variations "
                     f"have to end up in the same binning node")
        weights = compute_weights(dt_hist, mc_hist, args.max_rel_error)
        print(f"{key:<7} {path}")
        print(f"        {len(weights)} bins over [{edges[0]:g}, {edges[-1]:g}], "
              f"weights {min(weights):.4f} - {max(weights):.4f}")
        content.append({
            "key": key,
            "value": {
                "nodetype": "binning",
                "input": args.input_name,
                "flow": "clamp",
                "edges": edges,
                "content": weights,
            },
        })

    name = args.name
    if not name:
        name = os.path.basename(args.output).split(".")[0]
        name = name[len("puWeights_"):] if name.startswith("puWeights_") else name

    correction = {
        "name": name,
        "version": args.version,
        "inputs": [
            {"name": args.input_name, "type": "real", "description": "Number of interactions"},
            {"name": "weights", "type": "string",
             "description": ", ".join(key for key, _ in variations)},
        ],
        "output": {"name": "weight", "type": "real",
                   "description": "Event weight for pileup reweighting"},
        "data": {"nodetype": "category", "input": "weights", "content": content},
    }
    if args.description:
        correction["description"] = args.description

    cset = {"schema_version": 2, "corrections": [correction]}

    path = os.path.dirname(args.output)
    if path and not os.path.exists(path):
        os.makedirs(path)

    opener = gzip.open if args.output.endswith(".gz") else open
    with opener(args.output, "wt") as f:
        json.dump(cset, f, indent=2)
        f.write("\n")
    print(f"Wrote {args.output} with correction {name}")

    if args.validate:
        try:
            import correctionlib
        except ImportError:
            print("correctionlib is not importable, skipping the validation. "
                  "It is a CMSSW external, so `source activate_environment.sh` first.")
            sys.exit(0)
        try:
            from correctionlib.schemav2 import CorrectionSet
            # model_validate on pydantic 2, parse_obj on pydantic 1
            validate = getattr(CorrectionSet, "model_validate", None) or CorrectionSet.parse_obj
            validate(cset)
            print("Schema validation passed")
        except ImportError:
            print("correctionlib.schemav2 is not importable (it needs pydantic), "
                  "only evaluating the file")
        evaluator = correctionlib.CorrectionSet.from_file(args.output)[name]
        centres = [(edges[i] + edges[i + 1]) / 2 for i in range(len(edges) - 1)]
        for key, _ in variations:
            values = [round(evaluator.evaluate(x, key), 4) for x in centres]
            print(f"{key:<7} {values}")
