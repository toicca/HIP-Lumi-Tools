import numpy as np
import subprocess
import pandas as pd
import io
import argparse
import json
import configparser

def run_prescales(run, trg):
    print(f"Getting prescales for run {run} and trigger {trg}")

    # Dumb ahh solution
    bc_alias = "singularity -s exec  --env PYTHONPATH=/home/bril/.local/lib/python3.10/site-packages /cvmfs/unpacked.cern.ch/gitlab-registry.cern.ch/cms-cloud/brilws-docker:latest brilcalc"
    brilcall = [f"{bc_alias} trg -r {str(run)} --prescale --hltpath {str(trg)+'_v*'} --output-style csv"]

    command = subprocess.run(brilcall, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True, executable="/bin/bash")

    if command.returncode != 0:
        print(f"Error: {command.stderr}")
        return None
    else:
        csv_output = command.stdout
        df = pd.read_csv(io.StringIO(csv_output), usecols=["cmsls", "totprescval"], dtype={"cmsls": np.int32, "totprescval": np.float64})

    return df

if __name__ == "__main__":
    # Create a parser for the input json file
    parser = argparse.ArgumentParser(description="Produce a prescale JSON file")
    parser.add_argument("--json", type=str, required=True, help="The input JSON file")
    parser.add_argument("--output", type=str, help="The output JSON file")
    trg_group = parser.add_mutually_exclusive_group(required=True)
    trg_group.add_argument("--triggers", type=str, help="The triggers to get prescales for separated by commas")
    trg_group.add_argument("--trigger_config", type=str, help="Trigger config file used for JEC4PROMPT")
    trg_group.add_argument("--trigger_file", type=str, help="File with triggers to get prescales for")

    args = parser.parse_args()

    input_json = args.json
    if args.triggers:
        triggers = args.triggers.split(",")
    elif args.trigger_config:
        config = configparser.ConfigParser()
        config.read(args.trigger_config)
        triggers = config.sections()
    elif args.trigger_file:
        with open(args.trigger_file, "r") as f:
            triggers = f.read().splitlines()

    # Read the JSON file
    with open(input_json, "r") as f:
        data = json.load(f)

    runs = data.keys()
    last_lumisection = {run: data[run][-1][1] for run in runs}

    dfs = []
    output = {}
    for run in runs:
        output[run] = {}
        for trg in triggers:
            df = run_prescales(run, trg)

            for index, row in df.iterrows():
                if index < len(df) - 1:
                    if f'{int(row["cmsls"])},{int(df.iloc[index+1]["cmsls"])}' not in output[run]:
                        output[run][f'{int(row["cmsls"])},{int(df.iloc[index+1]["cmsls"])}'] = {}
                    output[run][f'{int(row["cmsls"])},{int(df.iloc[index+1]["cmsls"])}'][trg] = row["totprescval"]
                else:
                    if f'{int(row["cmsls"])},{int(last_lumisection[run])}' not in output[run]:
                        output[run][f'{int(row["cmsls"])},{int(last_lumisection[run])}'] = {}
                    output[run][f'{int(row["cmsls"])},{int(last_lumisection[run])}'][trg] = row["totprescval"]

    output_file = args.output if args.output else "prescales.json"
    with open(output_file, "w") as f:
        json.dump(output, f, indent=4, sort_keys=True)