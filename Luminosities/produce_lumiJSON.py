import numpy as np
import subprocess
import pandas as pd
import io
import argparse
import json
import configparser

def run_lumis(json, run="", trg="", normtag="BRIL"):
    print(f"Getting luminosities for {json} {f'and run {run}' if run else ''} {f'and trigger {trg}' if run else ''}")

    # NOTE: THERE'S SET BEGIN AND END FLAGS
    bc_alias = "singularity -s exec  --env PYTHONPATH=/home/bril/.local/lib/python3.10/site-packages /cvmfs/unpacked.cern.ch/gitlab-registry.cern.ch/cms-cloud/brilws-docker:latest brilcalc"
    brilcall = [f"{bc_alias} lumi {'-r'+ str(run) if run else ''} -u /fb -i {json} {'--hltpath '+ str(trg)+'_v*' if trg else ''} --output-style csv --normtag /cvmfs/cms-bril.cern.ch/cms-lumi-pog/Normtags/normtag_{normtag}.json"]
    # --begin 367080 --end 367515 
    print(" ".join(brilcall))
    command = subprocess.run(brilcall, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

    if command.returncode != 0:
        print(f"Error: {command.stderr}")
        return None
    else:
        csv_output = command.stdout
        print(csv_output)
        # Get header as the second comment line
        head_idx = csv_output.find("#run:fill")
        header = csv_output[head_idx:csv_output.find("\n", head_idx)].split(",")

        df = pd.read_csv(io.StringIO(csv_output), comment="#", names=header)
        
        # Clean the dataframe
        df = df.dropna()
        df = df[["#run:fill", "recorded(/fb)"]]
        df[["run", "fill"]] = df["#run:fill"].str.split(":", expand=True)
        df = df.drop(columns=["#run:fill", "fill"])
        df = df.groupby("run").sum()
        df = df.reset_index()
        df["run"] = df["run"].astype(int)
        df["recorded(/fb)"] = df["recorded(/fb)"]

    return df

if __name__ == "__main__":
    # Create a parser for the input json file
    parser = argparse.ArgumentParser(description="Produce a file with recorded luminosity information")
    parser.add_argument("--json", type=str, required=True, help="The input JSON file")
    parser.add_argument("--output", type=str, help="The output file")
    parser.add_argument("--normtag", type=str, default="BRIL", help="The normtag to use for the lumi calculation")
    parser.add_argument("--output-style", type=str, choices=["json", "csv"], default="json", help="The output style of the file")
    parser.add_argument("--sum", action="store_true", help="Sum the luminosities for each run")
    trg_group = parser.add_mutually_exclusive_group()
    trg_group.add_argument("--triggers", type=str, help="The triggers to get prescales for separated by commas")
    trg_group.add_argument("--trigger_config", type=str, help="Trigger config file used for JEC4PROMPT")
    trg_group.add_argument("--trigger_file", type=str, help="File with triggers to get luminosities for")

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
    else:
        triggers = [""]

    lumis = {}

    for trg in triggers:
        lumis[trg] = run_lumis(input_json, trg=trg, normtag=args.normtag)

    if args.output:
        output = args.output
        # Check if the output file has the correct extension
        if args.output_style == "json" and not output.endswith(".json"):
            output += ".json"
        elif args.output_style == "csv" and not output.endswith(".csv"):
            output += ".csv"
    else:
        output = "lumis.json" if args.output_style == "json" else "lumis.csv"
    

    if args.output_style == "json":
        # Create a dictionary with the lumis
        out = {}
        for trg, df in lumis.items():
            if not trg:
                # run is the key and recorded(/fb) is the value
                if args.sum:
                    out["sum"] = df["recorded(/fb)"].sum()
                else:
                    out = {str(int(row["run"])): row["recorded(/fb)"] for _, row in df.iterrows()}

                break
            else:
                if args.sum:
                    out[trg] = {}
                    out[trg]["sum"] = df["recorded(/fb)"].sum()
                else:
                    out[trg] = {str(int(row["run"])): row["recorded(/fb)"] for _, row in df.iterrows()}

        with open(output, "w") as f:
            json.dump(out, f)

    elif args.output_style == "csv":
        # Add trigger name to the dataframe
        for trg, df in lumis.items():
            if trg:
                df["trigger"] = trg

        # Concatenate all the dataframes
        df = pd.concat(lumis.values())
        df.to_csv(output, index=False)