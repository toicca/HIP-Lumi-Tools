import json
import os
import argparse
import subprocess
import copy
from typing import List, Dict

def parse_args():
    parser = argparse.ArgumentParser()
    dataset_group = parser.add_mutually_exclusive_group(required=True)
    dataset_group.add_argument('--datasets', type=str, nargs='+', help='Dataset names')
    dataset_group.add_argument('--dataset_file', type=str, help='File containing dataset names')
    dataset_group.add_argument('--dataset_query', type=str, help='Dataset query')
    output_group = parser.add_mutually_exclusive_group(required=True)
    output_group.add_argument('--output_dir', type=str, help='Output directory')
    output_group.add_argument('--extend_json', type=str, help='Extend JSON file with the output')
    parser.add_argument('--file_prefix', type=str, default='root://cms-xrd-global.cern.ch/', help='File prefix')
    parser.add_argument('--maxEvents', type=int, default=-1, help='Maximum number of events to process')

    return parser.parse_args()

def find_parent(dataset: str) -> str:
    call = f'/cvmfs/cms.cern.ch/common/dasgoclient --query="parent dataset={dataset}"'
    print(f'/cvmfs/cms.cern.ch/common/dasgoclient --query="parent dataset={dataset}"')
    os.system(call)

    parents = os.popen(call).read().split('\n')[0:-1]

    return parents[0]

def find_dataset(dataset_query: str, is_query=True) -> List[str]:
    call = f'/cvmfs/cms.cern.ch/common/dasgoclient --query="{dataset_query}"'
    print(f'/cvmfs/cms.cern.ch/common/dasgoclient --query="{dataset_query}"')
    os.system(call)

    result = os.popen(call).read()

    # Get each line as a dataset
    datasets = result.split('\n')[0:-1]
    
    return datasets

def find_files(dataset: str) -> List[str]:
    call = f'/cvmfs/cms.cern.ch/common/dasgoclient --query="file dataset={dataset}"'
    os.system(call)

    files = os.popen(call).read().split('\n')[0:-1]
    # result[dataset[1]] = files

    return files

def find_xsec(dataset: str, files: List[str], file_prefix: str = 'root://cms-xrd-global.cern.ch/', maxEvents: int = -1) -> Dict[str, float]:

    file_string = ''.join([file_prefix + file + "," for file in files])
    file_string = file_string[:-1]

    if not os.environ.get('LUMIENV'):
        raise Exception('LUMIENV environment variable not set')

    # Write input files to a temporary file with one file per line
    with open(f'{os.environ["LUMIENV"]}/Xsec/input_files.txt', 'w') as f:
        for file in files:
            f.write(f'{file_prefix}{file}\n')

    # call = [f'cmsRun', f'{os.environ["LUMIENV"]}/Xsec/genXsec_cfg.py' ,f'inputFiles="{file_string}"', 'maxEvents=1000']
    call = [f'cmsRun', f'{os.environ["LUMIENV"]}/Xsec/genXsec_cfg.py' ,f'inputFiles_load={os.environ["LUMIENV"]}/Xsec/input_files.txt', f'maxEvents={maxEvents}']
    # os.system(' '.join(call))
    process = subprocess.Popen(call, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, error = process.communicate()
    output = output + error

    os.system(f'rm {os.environ["LUMIENV"]}/Xsec/input_files.txt')

    target_xsec_string = 'After filter: final cross'
    target_event_string = 'Filter efficiency (event-level)'
    found_xsec = False
    found_event_number = False
    # Process the output in reverse order
    position = len(output) - 1
    buffer = b''

    while position >= 0:
        next_byte = output[position:position+1]
        if next_byte == b'\n' and buffer:
            line = buffer[::-1].decode()
            if target_xsec_string in line and not found_xsec:
                # xsec = float(line.split()[6])
                xsec = line.split(" = ")[1]
                found_xsec = True
                print(f'Found xsec {xsec} for {dataset}')
            if target_event_string in line and not found_event_number:
                event_number = line.split()[3]
                event_number = int(float(event_number[1:-1]))
                found_event_number = True
                print(f'Found nevents {event_number} for {dataset}')
            if found_xsec and found_event_number:
                break
            buffer = b''
        else:
            buffer += next_byte
        position -= 1

    if not (found_xsec and found_event_number):
        raise Exception(f'Could not find xsec or event number for dataset {dataset}')

    # Handle the case if the first line does not end with a newline
    if buffer and not (found_xsec and found_event_number):
        line = buffer[::-1].decode()
        if target_xsec_string in line and not found_xsec:
            xsec = line.split(" = ")[1]
            found_xsec = True
        if target_event_string in line and not found_event_number:
            event_number = line.split()[3]
            event_number = int(float(event_number[1:-1]))
            found_event_number = True


    return xsec, event_number

if __name__ == '__main__':
    args = parse_args()
    if args.datasets:
        args.datasets = list(set(args.datasets))
        print('Datasets provided:')
        print("\t",args.datasets)
        children = copy.deepcopy(args.datasets)
        parents = [find_parent(dataset) for dataset in args.datasets]
        args.datasets = args.datasets # parents
    elif args.dataset_file:
        with open(args.dataset_file, 'r') as f:
            args.datasets = [line.strip() for line in f if line.strip()]
        children = copy.deepcopy(args.datasets)
        args.datasets = [find_parent(dataset) for dataset in args.datasets]
    else:
        args.datasets = find_dataset(args.dataset_query)
        children = copy.deepcopy(args.datasets)
        args.datasets = [find_parent(dataset) for dataset in args.datasets]

    results = {}
    for dataset in args.datasets:
        print(f'Processing dataset: {dataset}')
        files = find_files(dataset)

        print(f'\tFound {len(files)} files for dataset {dataset}')

        print(f'\tProcessing files for dataset: {dataset}')
        xsec, nevents = find_xsec(dataset, files, args.file_prefix, args.maxEvents)
        print(f'\tFinished processing files for dataset: {dataset}')
        print()
        xsec_parts = xsec.split(' ')
        xsec_val = float(xsec_parts[0])
        xsec_unc = float(xsec_parts[2]) 
        rel_unc = xsec_unc / xsec_val if xsec_val != 0 else 0
        print(f'\033[95mDataset: {dataset}\033[0m')
        print(f'\033[92mCross section: {xsec_val} +/- {xsec_unc} (rel_unc: {rel_unc})\nNumber of generated events: {nevents}\033[0m')
        results[dataset] = {"xsec": xsec_val, "nGenEvents": nevents, "abs_unc": xsec_unc, "rel_unc": rel_unc}


    # Check that output dir exists
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    if args.output_dir:
        with open(f'{args.output_dir}/xsec.json', 'w') as f:
            json.dump(results, f, indent=4)
    else:
        with open(args.extend_json, 'r') as f:
            xsecs = json.load(f)

        xsecs.update(results)

        with open(args.extend_json, 'w') as f:
            json.dump(xsecs, f, indent=4)

