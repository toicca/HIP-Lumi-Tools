#!/usr/bin/env python3

import json
import os
import argparse, configparser
import re

def read_input():
    parser = argparse.ArgumentParser(description='Combine JSON files')

    # Config or fileslisted
    input_type = parser.add_mutually_exclusive_group(required=True)
    input_type.add_argument('--listFile', type=str, help='Path to a file that lists JSON files to combine')
    input_type.add_argument('--files', type=str, nargs='+', help='List of JSON files to combine separated by spaces')
    parser.add_argument('--add_previous', action='store_true', help='Add possible runs from DCS JSONs to the start of the golden JSONs')
    args = parser.parse_args()

    if args.listFile:
        with open(args.listFile, 'r') as f:
            files = f.read().splitlines()
    else:
        files = args.files

    return files, args.add_previous

def combine_jsons(files, add_previous = False):
    goldens = []
    golden_eras = []
    golden_runs = []
    DCSs = []
    DCS_runs = []

    # Find golden JSONs
    for file in files:
        if "Golden" in file:
            goldens.append(file)

            # Check if Golden is for era or runs
            if "era" in file.lower():
                idx = file.find("era")
                golden_eras.append(file[idx+3:idx+4])
            else:
                parts = re.search(r'_(\d+)_(\d+)', file).groups()
        else:
            DCSs.append(file)
            parts = re.search(r'_(\d+)_(\d+)', file).groups()

    # Join the golden jsons
    golden_json = {}
    for file in goldens:
        with open(file, 'r') as f:
            data = json.load(f)
            golden_json.update(data)

    golden_keys = sorted(golden_json.keys())
    golden_runs_min = golden_keys[0]
    golden_runs_max = golden_keys[-1]
    golden_runs.append(str(golden_runs_min) + "to" + str(golden_runs_max))

    # Join the DCS jsons
    for i, file in enumerate(DCSs):
        with open(file, 'r') as f:
            data = json.load(f)

            DCS_keys = sorted(data.keys())

            # Remove keys covered by golden runs
            for key in DCS_keys:
                if key < golden_runs_min and not add_previous:
                    del data[key]
                elif key < golden_runs_min and add_previous:
                    continue
                elif key <= golden_runs_max:
                    del data[key]

            DCS_keys = sorted(data.keys())
            if len(DCS_keys) > 0:
                if add_previous:
                    DCS_runs_min = DCS_keys[0]
                    DCS_runs.append(str(DCS_runs_min) + "to" + str(golden_runs_min))

                DCS_runs_max = DCS_keys[-1]
                DCS_runs.append(str(int(golden_runs_max)+1) + "to" + str(DCS_runs_max))

            golden_json.update(data)

    # Write the combined JSON
    file_name = "CombinedJSONS_"
    if len(golden_eras) > 0:
        file_name += "GoldenEras_" + "_".join(golden_eras) + "_"
    if len(golden_runs) > 0:
        file_name += "GoldenRuns_" + "_".join(golden_runs) + "_"
    if len(DCS_runs) > 0:
        file_name += "DCSRuns_" + "_".join(DCS_runs) + "_"
    file_name += ".json"

    with open(file_name, 'w') as f:
        json.dump(golden_json, f, indent=4, sort_keys=True)

    print("Golden JSONs: ", goldens)
    print("DCS JSONs: ", DCSs)
    print("Golden ERAs: ", golden_eras)
    print("Golden runs: ", golden_runs)
    print("DCS runs: ", DCS_runs)

if __name__ == '__main__':
    files, add_previous = read_input()
    combine_jsons(files, add_previous)

