import json
import os
import argparse
import subprocess
from typing import List, Dict

def parse_args():
    parser = argparse.ArgumentParser()
    dataset_group = parser.add_mutually_exclusive_group(required=True)
    dataset_group.add_argument('--dataset', type=str, help='Dataset name')
    dataset_group.add_argument('--dataset_query', type=str, help='Dataset query')
    output_group = parser.add_mutually_exclusive_group(required=True)
    output_group.add_argument('--output_dir', type=str, help='Output directory')
    output_group.add_argument('--extend_json', type=str, help='Extend JSON file with the output')

    return parser.parse_args()

def find_parent(datasets: List[str]) -> List[str]:
    result = []
    for dataset in datasets:
        call = f'/cvmfs/cms.cern.ch/common/dasgoclient --query="parent dataset={dataset}"'
        print(f'/cvmfs/cms.cern.ch/common/dasgoclient --query="parent dataset={dataset}"')
        os.system(call)

        parents = os.popen(call).read().split('\n')[0:-1]
        result.extend(parents)

    return result

def find_dataset(dataset_query: str) -> List[str]:
    call = f'/cvmfs/cms.cern.ch/common/dasgoclient --query="dataset dataset={dataset_query}"'
    print(f'/cvmfs/cms.cern.ch/common/dasgoclient --query="dataset dataset={dataset_query}"')
    os.system(call)

    result = os.popen(call).read()

    # Get each line as a dataset
    datasets = result.split('\n')[0:-1]
    
    return datasets

def find_files(datasets: List[str]) -> Dict[str, List[str]]:
    result = {}
    for dataset in datasets:
        call = f'/cvmfs/cms.cern.ch/common/dasgoclient --query="file dataset={dataset}"'
        print(f'/cvmfs/cms.cern.ch/common/dasgoclient --query="file dataset={dataset}"')
        os.system(call)

        files = os.popen(call).read().split('\n')[0:-1]
        result[dataset] = files

    return result

def find_xsec(dataset_files: Dict[str, List[str]]) -> Dict[str, float]:
    xsecs = {}
    nevents = {}
    file_prefix = 'root://cms-xrd-global.cern.ch/'

    for dataset, files in dataset_files.items():
        file_string = ''.join([file_prefix + file + "," for file in files])
        file_string = file_string[:-1]

        call = f'cmsRun {os.environ["LUMIENV"]}/Xsec/genXsec_cfg.py inputFiles="{file_string}" maxEvents=-1'
        process = subprocess.Popen(call, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        output = output + error

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
                    xsec = float(line.split()[6])
                    xsecs[dataset] = xsec
                    found_xsec = True
                    print(f'Found xsec for {dataset}: {xsec}')
                if target_event_string in line and not found_event_number:
                    event_number = line.split()[3]
                    event_number = int(float(event_number[1:-1]))
                    nevents[dataset] = event_number
                    found_event_number = True
                    print(f'Found nevents for {dataset}: {event_number}')
                if found_xsec and found_event_number:
                    break
                buffer = b''
            else:
                buffer += next_byte
            position -= 1

        # Handle the case if the first line does not end with a newline
        if buffer and not (found_xsec and found_event_number):
            line = buffer[::-1].decode()
            if target_xsec_string in line and not found_xsec:
                xsec = float(line.split()[6])
                xsecs[dataset] = xsec
                found_xsec = True
            if target_event_string in line and not found_event_number:
                event_number = line.split()[3]
                event_number = int(float(event_number[1:-1]))
                nevents[dataset] = event_number
                found_event_number = True


    return xsecs, nevents

if __name__ == '__main__':
    args = parse_args()
    if args.dataset:
        args.dataset = [args.dataset]
        args.dataset = find_parent(args.dataset)
    else:
        args.dataset = find_dataset(args.dataset_query)
        args.dataset = find_parent(args.dataset)

    xsecs, nevents = find_xsec(find_files(args.dataset))
    
    results = {"xsec": xsecs, "nGenEvents": nevents}

    if args.output_dir:
        with open(f'{args.output_dir}/xsec.json', 'w') as f:
            json.dump(results, f)
    else:
        # TODO
        with open(args.extend_json, 'r') as f:
            xsecs = json.load(f)
        xsecs.update(xsecs)
        with open(args.extend_json, 'w') as f:
            json.dump(xsecs, f)

