#!/usr/bin/env python3
"""
Plot the pileup histograms produced by produce_pileupHist.py and
produce_pileupWeight.py as small multiples, one panel per input file.

Two modes:
  --mode data     one panel per data pileup histogram (default)
  --mode weights  one panel per weights file, data vs MC on top and the
                  data/MC weights underneath

Usage:
    python3 Pileup/plot_pileupHists.py --mode data \
        --files output/2026_lowPU/pileup_2026_lowPU_69200ub.root ... \
        --labels "all,pu1,pu2" --output output/2026_lowPU/pileup_distributions
"""

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import ROOT

ROOT.gROOT.SetBatch(True)

DATA = "#2a78d6"      # categorical slot 1
MC = "#eb6834"        # categorical slot 2
INK = "#0b0b0b"
MUTED = "#8a8985"
GRID = "#e3e2de"


def parse_arguments():
    parser = argparse.ArgumentParser(description="Plot pileup histograms as small multiples")
    parser.add_argument("--files", nargs="+", required=True, help="Input ROOT files, one panel each")
    parser.add_argument("--labels", type=str, default="", help="Comma separated panel labels (default: file basenames)")
    parser.add_argument("--mode", choices=["data", "weights"], default="data", help="data: one pileup histogram per panel. weights: data vs MC plus the data/MC ratio")
    parser.add_argument("--hist", type=str, default="pileup", help="Histogram name to read in --mode data (default: pileup)")
    parser.add_argument("--output", "-o", type=str, required=True, help="Output path without extension")
    parser.add_argument("--title", type=str, default="", help="Figure title")
    parser.add_argument("--xmax", type=float, default=0, help="Upper limit of the pileup axis (default: auto per panel)")
    parser.add_argument("--ncols", type=int, default=0, help="Number of columns in the grid (default: auto)")
    parser.add_argument("--log", action="store_true", help="Log y axis")
    parser.add_argument("--xlabel", type=str, default="True pileup", help="Pileup axis label. Use 'Observed pileup' for histograms made with --calcMode observed")
    return parser.parse_args()


def read_hist(path, name):
    f = ROOT.TFile(path, "READ")
    if not f or f.IsZombie():
        raise RuntimeError(f"Cannot open {path}")
    h = f.Get(name)
    if not h:
        raise RuntimeError(f"No histogram {name!r} in {path}, found "
                           f"{[k.GetName() for k in f.GetListOfKeys()]}")
    edges = np.array([h.GetXaxis().GetBinLowEdge(i) for i in range(1, h.GetNbinsX() + 2)])
    values = np.array([h.GetBinContent(i) for i in range(1, h.GetNbinsX() + 1)])
    errors = np.array([h.GetBinError(i) for i in range(1, h.GetNbinsX() + 1)])
    f.Close()
    return edges, values, errors


def mean_of(edges, values):
    centres = 0.5 * (edges[:-1] + edges[1:])
    total = values.sum()
    return float((centres * values).sum() / total) if total > 0 else 0.0


def auto_xmax(edges, values, frac=0.9995):
    """Smallest upper edge holding `frac` of the integral, rounded up a little."""
    total = values.sum()
    if total <= 0:
        return edges[-1]
    cumulative = np.cumsum(values) / total
    idx = int(np.searchsorted(cumulative, frac))
    idx = min(idx, len(edges) - 2)
    return float(edges[idx + 1]) * 1.15


def style_axis(ax, log=False):
    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelcolor=INK, labelsize=8)
    if log:
        ax.set_yscale("log")


def grid_shape(n, ncols=0):
    if ncols <= 0:
        ncols = 3 if n > 4 else max(1, n)
    nrows = (n + ncols - 1) // ncols
    return nrows, ncols


def plot_data(files, labels, hist_name, output, title, xmax, ncols, log, xlabel="True pileup"):
    n = len(files)
    nrows, ncols = grid_shape(n, ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.0 * nrows), squeeze=False)

    for i, (path, label) in enumerate(zip(files, labels)):
        ax = axes[i // ncols][i % ncols]
        edges, values, _ = read_hist(path, hist_name)
        integral = values.sum()
        norm = values / integral if integral > 0 else values

        ax.stairs(norm, edges, fill=True, color=DATA, alpha=0.85, lw=0, zorder=2)
        style_axis(ax, log)
        ax.set_xlim(0, xmax if xmax else auto_xmax(edges, values))
        ax.set_title(label, loc="left", fontsize=10, color=INK)
        ax.annotate(f"$\\langle$PU$\\rangle$ = {mean_of(edges, values):.2f}\n"
                    f"{integral / 1e6:.1f} pb$^{{-1}}$",
                    xy=(0.97, 0.93), xycoords="axes fraction", ha="right", va="top",
                    fontsize=8, color=MUTED)
        if i // ncols == nrows - 1:
            ax.set_xlabel(xlabel, fontsize=9)
        if i % ncols == 0:
            ax.set_ylabel("Fraction of lumi / bin", fontsize=9)

    for j in range(n, nrows * ncols):
        axes[j // ncols][j % ncols].axis("off")

    if title:
        fig.suptitle(title, x=0.01, ha="left", fontsize=12, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.97 if title else 1))
    return fig


def plot_weights(files, labels, output, title, xmax, ncols, log, xlabel="True pileup"):
    n = len(files)
    nrows, ncols = grid_shape(n, ncols)
    fig, axes = plt.subplots(2 * nrows, ncols, figsize=(4.2 * ncols, 3.8 * nrows),
                             squeeze=False,
                             gridspec_kw={"height_ratios": [3, 1.4] * nrows})

    for i, (path, label) in enumerate(zip(files, labels)):
        row, col = i // ncols, i % ncols
        ax = axes[2 * row][col]
        ax_r = axes[2 * row + 1][col]

        edges, dt, _ = read_hist(path, "pileup_data")
        _, mc, _ = read_hist(path, "pileup_mc")
        _, w, w_err = read_hist(path, "weights")

        dt_n = dt / dt.sum() if dt.sum() > 0 else dt
        mc_n = mc / mc.sum() if mc.sum() > 0 else mc

        ax.stairs(dt_n, edges, fill=True, color=DATA, alpha=0.75, lw=0, zorder=2, label="data")
        ax.stairs(mc_n, edges, color=MC, lw=2, zorder=3, label="MC")
        style_axis(ax, log)
        limit = xmax if xmax else max(auto_xmax(edges, dt), auto_xmax(edges, mc))
        ax.set_xlim(0, limit)
        ax.set_title(label, loc="left", fontsize=10, color=INK)
        ax.tick_params(labelbottom=False)
        if col == 0:
            ax.set_ylabel("Normalised", fontsize=9)
        if i == 0:
            ax.legend(frameon=False, fontsize=8, labelcolor=INK, loc="upper right")

        centres = 0.5 * (edges[:-1] + edges[1:])
        ax_r.axhline(1.0, color=MUTED, lw=1, ls=(0, (4, 4)), zorder=1)
        ax_r.errorbar(centres, w, yerr=w_err, fmt="o", ms=2.5, color=DATA,
                      ecolor=DATA, elinewidth=0.8, zorder=2)
        style_axis(ax_r)
        ax_r.set_xlim(0, limit)
        inside = (centres < limit) & (w > 0)
        if inside.any():
            ax_r.set_ylim(0, min(3.0, 1.25 * float(np.max(w[inside]))))
        ax_r.set_xlabel(xlabel, fontsize=9)
        if col == 0:
            ax_r.set_ylabel("data / MC", fontsize=9)

    for j in range(n, nrows * ncols):
        axes[2 * (j // ncols)][j % ncols].axis("off")
        axes[2 * (j // ncols) + 1][j % ncols].axis("off")

    if title:
        fig.suptitle(title, x=0.01, ha="left", fontsize=12, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.97 if title else 1))
    return fig


if __name__ == "__main__":
    args = parse_arguments()

    labels = [l.strip() for l in args.labels.split(",") if l.strip()]
    if not labels:
        labels = [os.path.basename(f).replace(".root", "") for f in args.files]
    if len(labels) != len(args.files):
        sys.exit(f"{len(labels)} label(s) for {len(args.files)} file(s)")

    missing = [f for f in args.files if not os.path.exists(f)]
    if missing:
        sys.exit(f"Missing input file(s): {missing}")

    if args.mode == "data":
        fig = plot_data(args.files, labels, args.hist, args.output, args.title,
                        args.xmax, args.ncols, args.log, args.xlabel)
    else:
        fig = plot_weights(args.files, labels, args.output, args.title,
                           args.xmax, args.ncols, args.log, args.xlabel)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    for ext in ("png", "pdf"):
        path = f"{args.output}.{ext}"
        fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
        print(f"Wrote {path}")
    plt.close(fig)
