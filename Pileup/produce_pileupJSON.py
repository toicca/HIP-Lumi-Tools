#!/usr/bin/env python3
"""
Produce a per-lumisection pileup JSON (the input that pileupCalc.py expects as
--inputLumiJSON) for a period that has no official one published under
/eos/user/c/cmsdqm/www/CAF/certification/<era>/PileUp/.

The chain is the standard one described in
https://twiki.cern.ch/twiki/bin/viewauth/CMS/PileupJSONFileforData :

    brilcalc lumi --byls --xing   ->  per-BX luminosity CSV
    makePileupJSON.py             ->  {run: [[ls, xsecPU, RMS, avgPU], ...]}

brilcalc is called once per run so that the (very large) --xing CSV is produced
in resumable chunks; a run whose CSV already exists in --work-dir is skipped.

Usage:
    python3 Pileup/produce_pileupJSON.py \
        --lumijson /cvmfs/cms-griddata.cern.ch/cat/metadata/DC/Collisions26/latest/Cert_Collisions2026_lowPU.json \
        --output Data/pileup_JSON-2026_lowPU.txt
"""

import argparse
import json
import os
import subprocess
import sys

BRILCALC = "singularity -s exec --env PYTHONPATH=/home/bril/.local/lib/python3.10/site-packages /cvmfs/unpacked.cern.ch/gitlab-registry.cern.ch/cms-cloud/brilws-docker:latest brilcalc"
BRILWS_ENV = "/cvmfs/cms-bril.cern.ch/cms-lumi-pog/brilws-docker/brilws-env"


def parse_arguments():
    parser = argparse.ArgumentParser(description="Produce a per-LS pileup JSON for pileupCalc.py")
    parser.add_argument("--lumijson", required=True, type=str, help="Luminosity block JSON file such as GoldenJSON or DCSOnly")
    parser.add_argument("--output", required=True, type=str, help="Output pileup JSON file")
    parser.add_argument("--work-dir", type=str, default="", help="Directory for the per-run --xing CSVs (default: <output dir>/xing)")
    parser.add_argument("--normtag", type=str, choices=["BRIL", "PHYSICS"], default="BRIL", help="Normtag to use in brilcalc call (default: BRIL)")
    parser.add_argument("--ignore-normtag", action="store_true", help="Ignore the normtag in brilcalc call")
    parser.add_argument("--no-threshold", action="store_true", help="Pass -n to makePileupJSON.py, disabling the afterglow bunch threshold. Needed when the per-BX luminosity is genuinely low, e.g. for special low pileup runs.")
    parser.add_argument("--sel-bx", type=str, default="", help="Comma separated list of BXs to use (passed to makePileupJSON.py -b)")
    parser.add_argument("--force", action="store_true", help="Re-run brilcalc even for runs whose CSV already exists")

    return parser.parse_args()


def ensure_singularity_bindpath():
    """
    The BRILCALC image needs /cvmfs, /eos and /afs bound. activate_environment.sh
    does this by sourcing brilws-env, but the scripts are often run without it,
    in which case singularity fails with "a shared library is likely missing".
    """
    if os.environ.get("SINGULARITY_BINDPATH"):
        return

    out = subprocess.run(
        f'source {BRILWS_ENV} >/dev/null 2>&1; echo "$SINGULARITY_BINDPATH"',
        shell=True, executable="/bin/bash", capture_output=True, text=True,
    )
    bindpath = out.stdout.strip()
    if bindpath:
        os.environ["SINGULARITY_BINDPATH"] = bindpath
        os.environ["APPTAINER_BINDPATH"] = bindpath


def run_brilcalc_xing(lumijson, run, output_csv, normtag="BRIL", ignore_normtag=False):
    """Call brilcalc for a single run, writing the per-BX CSV to output_csv."""
    call = f"{BRILCALC} lumi --byls --xing -r {run} -i {lumijson} -o {output_csv}"
    if not ignore_normtag:
        call += f" --normtag /cvmfs/cms-bril.cern.ch/cms-lumi-pog/Normtags/normtag_{normtag}.json"

    print("-----------------------------------")
    print(call)
    rc = os.system(call)
    if rc != 0 or not os.path.exists(output_csv):
        print(f"\033[91mbrilcalc failed for run {run}\033[0m", file=sys.stderr)
        return False
    return True


def combine_csvs(csv_files, combined_csv):
    """Concatenate the per-run CSVs in run order, keeping a single header."""
    with open(combined_csv, "w") as out:
        for i, csv_file in enumerate(csv_files):
            with open(csv_file) as f:
                for line in f:
                    # makePileupJSON.py skips '#' lines anyway, but keep the file readable
                    if line.startswith("#") and i > 0:
                        continue
                    out.write(line)
    return combined_csv


def make_pileup_json(combined_csv, output, no_threshold=False, sel_bx=""):
    call = f"makePileupJSON.py {combined_csv} {output}"
    if no_threshold:
        call += " -n"
    if sel_bx:
        call += f" -b {sel_bx}"

    print("Calling makePileupJSON.py")
    print("-----------------------------------")
    print(call)
    return os.system(call)


if __name__ == "__main__":
    args = parse_arguments()
    ensure_singularity_bindpath()

    with open(args.lumijson) as f:
        runs = sorted(int(run) for run in json.load(f))
    print(f"{len(runs)} run(s) in {args.lumijson}")

    output_dir = os.path.dirname(os.path.abspath(args.output))
    work_dir = args.work_dir if args.work_dir else os.path.join(output_dir, "xing")
    os.makedirs(work_dir, exist_ok=True)

    csv_files = []
    failed = []
    for i, run in enumerate(runs):
        output_csv = os.path.join(work_dir, f"{run}.csv")
        if os.path.exists(output_csv) and os.path.getsize(output_csv) > 0 and not args.force:
            print(f"[{i+1}/{len(runs)}] run {run}: reusing {output_csv}")
            csv_files.append(output_csv)
            continue

        print(f"[{i+1}/{len(runs)}] run {run}")
        if run_brilcalc_xing(args.lumijson, run, output_csv, args.normtag, args.ignore_normtag):
            csv_files.append(output_csv)
        else:
            failed.append(run)

    if failed:
        print(f"\033[91mbrilcalc failed for {len(failed)} run(s): {failed}\033[0m", file=sys.stderr)
    if not csv_files:
        sys.exit("No per-BX CSV was produced, cannot continue.")

    combined_csv = os.path.join(work_dir, "combined.csv")
    print(f"Combining {len(csv_files)} CSV(s) into {combined_csv}")
    combine_csvs(csv_files, combined_csv)

    rc = make_pileup_json(combined_csv, args.output, args.no_threshold, args.sel_bx)
    if rc != 0:
        sys.exit("makePileupJSON.py failed")

    print(f"\033[92mOutput file: {args.output}\033[0m")
    if failed:
        sys.exit(1)
