#!/usr/bin/env python3
"""
Compute the luminosity-weighted average pileup (avgpu) per run, or show
the avgpu for each individual lumisection, from a brilcalc --xing CSV file.

Usage:
    python avgpu_per_run.py lumi_DCSONLY.csv
    python avgpu_per_run.py lumi_DCSONLY.csv --by-ls
    python avgpu_per_run.py lumi_DCSONLY.csv --golden --min-pu 4 --max-pu 6 -o pu4to6.json
    python avgpu_per_run.py lumi_DCSONLY.csv --output avgpu.json
    python avgpu_per_run.py lumi_DCSONLY.csv --split-pu --split-dir output/
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compute luminosity-weighted average PU per run from a brilcalc CSV."
    )
    parser.add_argument("csv", help="Input brilcalc CSV file (with --xing output).")
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Write results as JSON to this file. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--min-pu",
        type=float,
        default=None,
        help="Only include runs with average PU >= this value.",
    )
    parser.add_argument(
        "--max-pu",
        type=float,
        default=None,
        help="Only include runs/lumisections with average PU <= this value.",
    )
    parser.add_argument(
        "--by-ls",
        action="store_true",
        default=False,
        help="Show avgpu for each lumisection instead of per-run averages.",
    )
    parser.add_argument(
        "--golden",
        action="store_true",
        default=False,
        help=(
            "Output a CMS golden JSON grouping lumisections that pass the "
            "--min-pu/--max-pu filter into contiguous ranges per run."
        ),
    )
    parser.add_argument(
        "--split-pu",
        action="store_true",
        default=False,
        help=(
            "Write one golden JSON per pileup band, splitting on the per-lumisection "
            "avgpu. Use for periods that mix several pileup points in the same runs."
        ),
    )
    parser.add_argument(
        "--pu-bands",
        type=str,
        default="0-1,2-3,4-6,7-100",
        help=(
            "Comma separated, inclusive bands of rounded per-LS avgpu for --split-pu "
            "(default: 0-1,2-3,4-6,7-100)."
        ),
    )
    parser.add_argument(
        "--band-names",
        type=str,
        default="",
        help=(
            "Comma separated names for the --pu-bands. By default each band is named "
            "pu<N> with N the rounded lumi-weighted average PU of the band."
        ),
    )
    parser.add_argument(
        "--split-prefix",
        type=str,
        default="lowPU",
        help="File name prefix for the --split-pu output (default: lowPU).",
    )
    parser.add_argument(
        "--split-dir",
        type=str,
        default=".",
        help="Directory for the --split-pu output (default: current directory).",
    )
    return parser.parse_args()


def _parse_csv(csv_path):
    """Yield (run, ls, recorded, avgpu) tuples from a brilcalc CSV."""
    with open(csv_path, newline="") as f:
        for raw_line in f:
            line = raw_line.strip()
            if line.startswith("#") or not line:
                continue

            # Split only the first 9 fields; the last column is the long BX data
            parts = line.split(",", 9)
            if len(parts) < 8:
                continue

            run_fill = parts[0].strip()    # e.g. "401866:11505"
            ls_str = parts[1].strip()      # e.g. "31:31"
            recorded_str = parts[6].strip()
            avgpu_str = parts[7].strip()

            try:
                run = int(run_fill.split(":")[0])
                ls = int(ls_str.split(":")[0])
                recorded = float(recorded_str)
                avgpu = float(avgpu_str)
            except (ValueError, IndexError):
                continue

            yield run, ls, recorded, avgpu


def compute_avgpu_per_run(csv_path):
    """
    Parse a brilcalc CSV and return a dict mapping run -> luminosity-weighted avgpu.
    """
    # Accumulators: run -> (sum of recorded*avgpu, sum of recorded)
    run_lumi_pu = defaultdict(lambda: [0.0, 0.0])

    for run, _ls, recorded, avgpu in _parse_csv(csv_path):
        run_lumi_pu[run][0] += recorded * avgpu
        run_lumi_pu[run][1] += recorded

    result = {}
    for run, (weighted_pu, total_lumi) in sorted(run_lumi_pu.items()):
        if total_lumi > 0:
            result[run] = round(weighted_pu / total_lumi)
        else:
            result[run] = 0

    return result


def compute_avgpu_by_ls(csv_path):
    """
    Parse a brilcalc CSV and return a dict mapping (run, ls) -> rounded avgpu.
    """
    result = {}
    for run, ls, _recorded, avgpu in _parse_csv(csv_path):
        result[(run, ls)] = round(avgpu)

    return dict(sorted(result.items()))


def compute_ls_data(csv_path):
    """
    Parse a brilcalc CSV and return a dict mapping
    (run, ls) -> (rounded_avgpu, recorded_lumi).
    """
    result = {}
    for run, ls, recorded, avgpu in _parse_csv(csv_path):
        result[(run, ls)] = (round(avgpu), recorded)

    return dict(sorted(result.items()))


def make_golden_json(ls_pu, min_pu=None, max_pu=None):
    """
    Given a dict of (run, ls) -> rounded avgpu, return a CMS golden JSON dict
    (run_str -> list of [ls_start, ls_end] ranges) for lumisections that pass
    the optional min_pu / max_pu filter.
    """
    # Collect passing LS per run in sorted order
    run_ls = defaultdict(list)
    for (run, ls), pu in sorted(ls_pu.items()):
        if min_pu is not None and pu < min_pu:
            continue
        if max_pu is not None and pu > max_pu:
            continue
        run_ls[run].append(ls)

    golden = {}
    for run, lss in sorted(run_ls.items()):
        ranges = []
        start = lss[0]
        end = lss[0]
        for ls in lss[1:]:
            if ls == end + 1:
                end = ls
            else:
                ranges.append([start, end])
                start = ls
                end = ls
        ranges.append([start, end])
        golden[str(run)] = ranges

    return golden


def parse_pu_bands(bands_str):
    """Parse "0-1,2-3" into [(0, 1), (2, 3)] of inclusive rounded-PU bounds."""
    bands = []
    for token in bands_str.split(","):
        token = token.strip()
        if not token:
            continue
        low, _, high = token.partition("-")
        bands.append((int(low), int(high if high else low)))
    return bands


def band_summary(ls_data, min_pu, max_pu):
    """Return (n_ls, recorded_lumi, lumi_weighted_avgpu) for one inclusive PU band."""
    n_ls = 0
    total_lumi = 0.0
    weighted_pu = 0.0
    for pu, recorded in ls_data.values():
        if pu < min_pu or pu > max_pu:
            continue
        n_ls += 1
        total_lumi += recorded
        weighted_pu += pu * recorded
    return n_ls, total_lumi, (weighted_pu / total_lumi if total_lumi > 0 else 0.0)


def _write_or_print_json(data, output_path, label):
    if output_path:
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Wrote {label} to {output_path}")
    else:
        print(json.dumps(data, indent=2))


def main():
    args = parse_args()

    if args.split_pu:
        ls_data = compute_ls_data(args.csv)
        ls_pu = {k: pu for k, (pu, _rec) in ls_data.items()}
        bands = parse_pu_bands(args.pu_bands)
        names = [n.strip() for n in args.band_names.split(",") if n.strip()]
        if names and len(names) != len(bands):
            sys.exit("--band-names must have as many entries as --pu-bands")

        total_ls = len(ls_data)
        total_lumi = sum(rec for _pu, rec in ls_data.values())
        covered_ls = 0
        covered_lumi = 0.0

        os.makedirs(args.split_dir, exist_ok=True)
        for i, (min_pu, max_pu) in enumerate(bands):
            golden = make_golden_json(ls_pu, min_pu=min_pu, max_pu=max_pu)
            n_ls, band_lumi, band_pu = band_summary(ls_data, min_pu, max_pu)
            if not golden:
                print(f"No lumisections in PU band {min_pu}-{max_pu}, skipping.", file=sys.stderr)
                continue

            name = names[i] if names else f"pu{round(band_pu)}"
            output_path = os.path.join(args.split_dir, f"{args.split_prefix}_{name}.json")
            with open(output_path, "w") as f:
                json.dump(golden, f, indent=2)

            covered_ls += n_ls
            covered_lumi += band_lumi
            print(
                f"{name:>8}  PU {min_pu:>3}-{max_pu:<4} "
                f"{len(golden):>3} run(s)  {n_ls:>6} LS  "
                f"{band_lumi / 1e6:9.3f} /pb ({100 * band_lumi / total_lumi if total_lumi else 0:6.3f}%)  "
                f"<PU> = {band_pu:.2f}  ->  {output_path}"
            )

        print(
            f"\nCovered {covered_ls}/{total_ls} LS and "
            f"{covered_lumi / 1e6:.3f}/{total_lumi / 1e6:.3f} /pb "
            f"({100 * covered_lumi / total_lumi if total_lumi else 0:.3f}%)",
            file=sys.stderr,
        )
        if covered_ls != total_ls:
            print(
                f"\033[93mWarning: {total_ls - covered_ls} LS fall outside the given "
                f"--pu-bands and are in no output file.\033[0m",
                file=sys.stderr,
            )
        return

    if args.golden:
        ls_data = compute_ls_data(args.csv)

        # Build a plain pu-only dict for make_golden_json
        ls_pu = {k: pu for k, (pu, _rec) in ls_data.items()}
        golden = make_golden_json(ls_pu, min_pu=args.min_pu, max_pu=args.max_pu)

        if not golden:
            print("No lumisections pass the PU filter.", file=sys.stderr)
            sys.exit(1)

        # Compute lumi-weighted average PU over the passing LS
        total_lumi = 0.0
        weighted_pu = 0.0
        for (run, ls), (pu, recorded) in ls_data.items():
            if args.min_pu is not None and pu < args.min_pu:
                continue
            if args.max_pu is not None and pu > args.max_pu:
                continue
            weighted_pu += pu * recorded
            total_lumi += recorded
        lumi_weighted_avg_pu = weighted_pu / total_lumi if total_lumi > 0 else 0.0

        n_ls = sum(e - s + 1 for ranges in golden.values() for s, e in ranges)
        label = f"golden JSON ({len(golden)} run(s), {n_ls} LS)"
        _write_or_print_json(golden, args.output, label)
        print(f"Lumi-weighted average PU of selected LS: {lumi_weighted_avg_pu:.2f} (rounded: {round(lumi_weighted_avg_pu)})", file=sys.stderr)
        return

    if args.by_ls:
        data = compute_avgpu_by_ls(args.csv)

        if args.min_pu is not None:
            data = {k: pu for k, pu in data.items() if pu >= args.min_pu}
        if args.max_pu is not None:
            data = {k: pu for k, pu in data.items() if pu <= args.max_pu}

        if not data:
            print("No data found in the CSV.", file=sys.stderr)
            sys.exit(1)

        if args.output:
            # Serialize (run, ls) tuples as "run:ls" strings
            with open(args.output, "w") as f:
                json.dump({f"{r}:{l}": pu for (r, l), pu in data.items()}, f, indent=2)
            print(f"Wrote avgpu for {len(data)} lumisection(s) to {args.output}")
        else:
            print(f"{'Run':>10}  {'LS':>6}  {'Avg PU':>6}")
            print("-" * 28)
            for (run, ls), pu in data.items():
                print(f"{run:>10}  {ls:>6}  {pu:>6}")
    else:
        avgpu = compute_avgpu_per_run(args.csv)

        if args.min_pu is not None:
            avgpu = {run: pu for run, pu in avgpu.items() if pu >= args.min_pu}
        if args.max_pu is not None:
            avgpu = {run: pu for run, pu in avgpu.items() if pu <= args.max_pu}

        if not avgpu:
            print("No data found in the CSV.", file=sys.stderr)
            sys.exit(1)

        if args.output:
            with open(args.output, "w") as f:
                json.dump({str(k): v for k, v in avgpu.items()}, f, indent=2)
            print(f"Wrote avgpu for {len(avgpu)} run(s) to {args.output}")
        else:
            print(f"{'Run':>10}  {'Avg PU':>6}")
            print("-" * 20)
            for run, pu in avgpu.items():
                print(f"{run:>10}  {pu:>6}")


if __name__ == "__main__":
    main()
