#!/usr/bin/env python3
"""
Plot the luminosity-weighted average pileup per run from a brilcalc --byls CSV.

Each run is drawn as a point at its lumi-weighted mean per-LS avgpu, with a bar
spanning the lumi-weighted 5th-95th percentile of the per-LS avgpu and a thin
whisker for the full min-max. Percentiles rather than an RMS because the runs
that ramp the pileup have an RMS larger than their mean, which a log axis cannot
draw. The lower panel shows the recorded luminosity per run, so the runs that
carry the luminosity are obvious.

Usage:
    python3 Pileup/plot_avgpu_per_run.py output/2026_lowPU/lowPU_byls.csv \
        --output output/2026_lowPU/avgpu_per_run \
        --title "2026 low pileup" --pu-bands 1.5,3.5,6.5,15.5,30.5
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.environ.get("LUMIENV", "."), "CommonTools"))
from avgpu_per_run import _parse_csv

# Single-series blue and recessive neutrals; see the data visualisation palette
SERIES = "#2a78d6"
INK = "#0b0b0b"
MUTED = "#8a8985"
GRID = "#e3e2de"


def _weighted_quantile(sorted_pairs, total, q):
    """Quantile of per-LS avgpu weighted by recorded luminosity."""
    target = q * total
    running = 0.0
    for pu, weight in sorted_pairs:
        running += weight
        if running >= target:
            return pu
    return sorted_pairs[-1][0]


def parse_arguments():
    parser = argparse.ArgumentParser(description="Plot average pileup per run from a brilcalc CSV")
    parser.add_argument("csv", help="Input brilcalc --byls CSV file")
    parser.add_argument("--output", "-o", type=str, default="avgpu_per_run", help="Output path without extension (default: avgpu_per_run)")
    parser.add_argument("--title", type=str, default="", help="Title annotation, eg. the era")
    parser.add_argument("--pu-bands", type=str, default="", help="Comma separated PU values to draw as reference lines, eg. the edges used by avgpu_per_run.py --split-pu")
    parser.add_argument("--band-labels", type=str, default="", help="Comma separated names for the regions between (and outside) the --pu-bands lines, drawn on the right hand side")
    parser.add_argument("--x-run-number", action="store_true", help="Use the run number as a numeric x axis instead of evenly spaced runs")
    parser.add_argument("--linear", action="store_true", help="Use a linear pileup axis instead of log")
    parser.add_argument("--note", type=str, default="", help="Extra note printed under the title, eg. the minimum bias cross section convention")
    return parser.parse_args()


def compute_run_stats(csv_path):
    """
    Return {run: dict} with the lumi-weighted mean and RMS of the per-LS avgpu,
    the min/max per-LS avgpu, the recorded luminosity and the number of LS.
    """
    per_run = defaultdict(list)
    for run, _ls, recorded, avgpu in _parse_csv(csv_path):
        per_run[run].append((recorded, avgpu))

    stats = {}
    for run, entries in sorted(per_run.items()):
        total_lumi = sum(rec for rec, _ in entries)
        if total_lumi > 0:
            mean = sum(rec * pu for rec, pu in entries) / total_lumi
            var = sum(rec * (pu - mean) ** 2 for rec, pu in entries) / total_lumi
        else:
            mean, var = 0.0, 0.0
        pus = [pu for _, pu in entries]
        by_pu = sorted(((pu, rec) for rec, pu in entries), key=lambda t: t[0])
        stats[run] = {
            "avgpu": mean,
            "rmspu": math.sqrt(var),
            "minpu": min(pus),
            "maxpu": max(pus),
            "p05pu": _weighted_quantile(by_pu, total_lumi, 0.05),
            "p50pu": _weighted_quantile(by_pu, total_lumi, 0.50),
            "p95pu": _weighted_quantile(by_pu, total_lumi, 0.95),
            "recorded_ub": total_lumi,
            "nls": len(entries),
        }
    return stats


def make_plot(stats, output, title="", bands=(), band_labels=(), x_run_number=False, log_y=True, note=""):
    runs = sorted(stats)
    x = runs if x_run_number else list(range(len(runs)))
    mean = [stats[r]["avgpu"] for r in runs]
    lumi_pb = [stats[r]["recorded_ub"] / 1e6 for r in runs]
    total_pb = sum(lumi_pb)

    floor = 0.85 * min(stats[r]["p05pu"] for r in runs)
    ceiling = 1.3 * max(stats[r]["p95pu"] for r in runs)
    quant = [[stats[r]["avgpu"] - stats[r]["p05pu"] for r in runs],
             [stats[r]["p95pu"] - stats[r]["avgpu"] for r in runs]]
    lo = [m - max(floor, stats[r]["minpu"]) for r, m in zip(runs, mean)]
    hi = [max(0.0, min(ceiling, stats[r]["maxpu"]) - stats[r]["avgpu"]) for r in runs]

    fig, (ax, ax_lumi) = plt.subplots(
        2, 1, figsize=(13, 7.5), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08},
    )

    # Reference lines for the pileup bands used to split the reweighting groups
    for band in bands:
        ax.axhline(band, color=GRID, lw=1, ls=(0, (4, 4)), zorder=0)
    if bands and band_labels:
        edges = [floor] + list(bands) + [ceiling]
        for name, low, high in zip(band_labels, edges[:-1], edges[1:]):
            centre = math.sqrt(low * high) if log_y else 0.5 * (low + high)
            ax.annotate(name, xy=(1.0, centre), xycoords=("axes fraction", "data"),
                        xytext=(6, 0), textcoords="offset points",
                        va="center", ha="left", fontsize=8, color=MUTED)
    elif bands:
        for band in bands:
            ax.annotate(f"{band:g}", xy=(1.0, band), xycoords=("axes fraction", "data"),
                        xytext=(6, 0), textcoords="offset points",
                        va="center", ha="left", fontsize=8, color=MUTED)

    # min-max of the per-LS pileup: recessive, it is a range not a measurement
    ax.errorbar(x, mean, yerr=[lo, hi], fmt="none", ecolor=MUTED, elinewidth=0.9,
                capsize=0, zorder=1, label="per-LS min-max")
    # lumi-weighted 5th-95th percentile: where the luminosity of the run actually sits
    ax.errorbar(x, mean, yerr=quant, fmt="none", ecolor=SERIES, elinewidth=3.2,
                capsize=0, alpha=0.5, zorder=2, label="per-LS 5-95% of lumi")
    # the measurement itself, marker area scaled by recorded luminosity
    max_lumi = max(lumi_pb) if lumi_pb else 1.0
    sizes = [18 + 130 * (l / max_lumi) for l in lumi_pb]
    ax.scatter(x, mean, s=sizes, color=SERIES, edgecolor="white", linewidth=0.8,
               zorder=3, label="lumi-weighted mean PU (area $\\propto$ recorded lumi)")

    if log_y:
        ax.set_yscale("log")
        ax.set_ylim(floor, ceiling)
        ticks = [t for t in (1, 2, 3, 5, 10, 20, 30, 50, 100) if floor <= t <= ceiling]
        ax.set_yticks(ticks)
        ax.set_yticklabels([str(t) for t in ticks])
        ax.minorticks_off()
    ax.set_ylabel("Average pileup")
    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelcolor=INK)
    leg = ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK)
    leg.set_zorder(5)

    header = title if title else "Average pileup per run"
    ax.set_title(header, loc="left", fontsize=13, color=INK, pad=22 if note else 14)
    if note:
        ax.annotate(note, xy=(0.0, 1.0), xycoords="axes fraction", xytext=(0, 8),
                    textcoords="offset points", ha="left", va="bottom",
                    fontsize=9, color=MUTED)
    ax.annotate(f"{len(runs)} runs, {total_pb:.1f} pb$^{{-1}}$ recorded",
                xy=(1.0, 1.0), xycoords="axes fraction", xytext=(0, 8),
                textcoords="offset points", ha="right", va="bottom",
                fontsize=9, color=MUTED)

    # Lower panel: where the luminosity actually is
    ax_lumi.bar(x, lumi_pb, width=0.62 if not x_run_number else 4, color=SERIES, zorder=2)
    ax_lumi.set_yscale("log")
    ax_lumi.set_ylabel("Recorded\n[pb$^{-1}$]")
    ax_lumi.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax_lumi.set_axisbelow(True)
    for side in ("top", "right"):
        ax_lumi.spines[side].set_visible(False)
    ax_lumi.spines["left"].set_color(GRID)
    ax_lumi.spines["bottom"].set_color(GRID)
    ax_lumi.tick_params(colors=MUTED, labelcolor=INK)

    if x_run_number:
        ax_lumi.set_xlabel("Run number")
    else:
        ax_lumi.set_xticks(x)
        ax_lumi.set_xticklabels([str(r) for r in runs], rotation=90, fontsize=7)
        ax_lumi.set_xlabel("Run number")
        ax_lumi.set_xlim(-1, len(runs))

    fig.align_ylabels([ax, ax_lumi])
    fig.subplots_adjust(left=0.075, right=0.955, top=0.92, bottom=0.16)

    for ext in ("png", "pdf"):
        path = f"{output}.{ext}"
        fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
        print(f"Wrote {path}")
    plt.close(fig)


if __name__ == "__main__":
    args = parse_arguments()

    stats = compute_run_stats(args.csv)
    if not stats:
        sys.exit("No data found in the CSV.")

    bands = [float(b) for b in args.pu_bands.split(",") if b.strip()] if args.pu_bands else []

    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)

    band_labels = [n.strip() for n in args.band_labels.split(",") if n.strip()]
    make_plot(stats, args.output, args.title, bands, band_labels,
              args.x_run_number, not args.linear, args.note)

    json_path = f"{args.output}.json"
    with open(json_path, "w") as f:
        json.dump({str(run): stats[run] for run in sorted(stats)}, f, indent=2)
    print(f"Wrote {json_path}")

    print(f"\n{'Run':>8} {'<PU>':>7} {'RMS':>7} {'p05':>6} {'p50':>6} {'p95':>6} "
          f"{'minPU':>6} {'maxPU':>6} {'rec/pb':>10} {'nLS':>6}")
    print("-" * 82)
    for run in sorted(stats):
        st = stats[run]
        print(f"{run:>8} {st['avgpu']:7.2f} {st['rmspu']:7.2f} {st['p05pu']:6.1f} "
              f"{st['p50pu']:6.1f} {st['p95pu']:6.1f} {st['minpu']:6.1f} "
              f"{st['maxpu']:6.1f} {st['recorded_ub'] / 1e6:10.3f} {st['nls']:>6}")
