import json
import os
import sys
import argparse
import subprocess
import copy
import traceback
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
    parser.add_argument('--retries', type=int, default=2, help='Number of times to retry a failed cmsRun job (transient xrootd errors)')

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

def _run_cmsrun(files: List[str], file_prefix: str, maxEvents: int):
    """Run the GenXSecAnalyzer cmsRun job over `files`.

    Returns (returncode, combined_output_bytes). A negative returncode means the
    process was killed by a signal (e.g. -9 = OOM killer).
    """
    lumienv = os.environ.get('LUMIENV')
    if not lumienv:
        raise Exception('LUMIENV environment variable not set')

    # Write input files to a temporary file with one file per line
    input_path = f'{lumienv}/Xsec/input_files.txt'
    with open(input_path, 'w') as f:
        for file in files:
            f.write(f'{file_prefix}{file}\n')

    call = ['cmsRun', f'{lumienv}/Xsec/genXsec_cfg.py',
            f'inputFiles_load={input_path}', f'maxEvents={maxEvents}']
    process = subprocess.Popen(call, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, error = process.communicate()

    os.system(f'rm {input_path}')

    return process.returncode, output + error

def _parse_xsec_output(combined: bytes):
    """Extract (xsec_string, event_number) from GenXSecAnalyzer output.

    Returns whatever was found; either element is None if its line is absent
    (which is what happens when cmsRun aborts before endJob). Keeps the last
    occurrence of each line, i.e. the final summary block.
    """
    text = combined.decode(errors='replace')
    xsec = None
    event_number = None
    for line in text.splitlines():
        if 'After filter: final cross' in line:
            # e.g. "After filter: final cross section = 1.072e-03 +- 8.726e-06 pb"
            xsec = line.split(' = ')[1].strip()
        elif 'Filter efficiency (event-level)' in line:
            # e.g. "Filter efficiency (event-level)= (13538) / (13538) = ..."
            try:
                event_number = int(float(line.split()[3][1:-1]))
            except (IndexError, ValueError):
                pass
    return xsec, event_number

def _extract_cmssw_exception(text: str) -> str:
    """Return the CMSSW fatal-exception block if present, else ''.

    This block (framework-generated) names the actual reason a cmsRun job died
    -- e.g. an unreadable input file, a missing product, or a segfault -- and is
    far more useful than a raw tail of the log.
    """
    start = text.find('----- Begin Fatal Exception')
    if start != -1:
        end = text.find('----- End Fatal Exception', start)
        end = text.find('\n', end) if end != -1 else -1
        return text[start:end if end != -1 else len(text)].strip()

    # Fall back to a bare category/message if the framed block is absent.
    idx = text.find('An exception of category')
    if idx != -1:
        return text[idx:idx + 600].strip()
    return ''

def _diagnose_cmsrun_failure(dataset: str, missing: List[str], returncode, combined: bytes,
                             files: List[str], maxEvents: int) -> str:
    """Build a human-readable diagnosis of why a cmsRun job produced no summary."""
    text = combined.decode(errors='replace')
    n_opened = text.count('Successfully opened file')

    killed = isinstance(returncode, int) and returncode < 0
    lines = [
        f'Could not find {" and ".join(missing)} for dataset {dataset}.',
        f'  cmsRun exit code : {returncode}' + (f'  (killed by signal {-returncode})' if killed else ''),
        f'  input files      : {len(files)}',
        f'  files opened     : {n_opened}/{len(files)}',
        f'  maxEvents        : {maxEvents}',
    ]

    # If a file-open request was issued but never succeeded, name the culprit file.
    last_req = text.rfind('Initiating request to open file ')
    if last_req != -1:
        nl = text.find('\n', last_req)
        req_line = text[last_req:nl if nl != -1 else len(text)]
        req_file = req_line.replace('Initiating request to open file ', '').strip()
        if req_file and f'Successfully opened file {req_file}' not in text:
            lines.append(f'  file NOT opened  : {req_file}')

    exc = _extract_cmssw_exception(text)
    if exc:
        lines.append('  --- CMSSW exception ---')
        lines.append(exc)
    else:
        tail = text.splitlines()[-40:]
        lines.append(f'  --- last {len(tail)} line(s) of cmsRun output ---')
        lines.extend(tail)
    return '\n'.join(lines)

def _save_failure_log(dataset: str, attempt: int, combined: bytes) -> str:
    """Dump the full cmsRun output for a failed attempt and return its path."""
    lumienv = os.environ.get('LUMIENV', '.')
    log_dir = f'{lumienv}/Xsec/failed_logs'
    os.makedirs(log_dir, exist_ok=True)
    safe = dataset.strip('/').replace('/', '__')
    log_path = f'{log_dir}/{safe}.attempt{attempt}.log'
    with open(log_path, 'wb') as f:
        f.write(combined)
    return log_path

def find_xsec(dataset: str, files: List[str], file_prefix: str = 'root://cms-xrd-global.cern.ch/', maxEvents: int = -1, retries: int = 2):
    """Compute (xsec_string, n_events) for `dataset` via GenXSecAnalyzer.

    Retries the cmsRun job on failure: the usual cause of a missing summary is a
    transient xrootd/file-open error during the run, which a re-run typically
    clears. On persistent failure the full log of each attempt is saved and a
    detailed diagnosis is raised.
    """
    if not files:
        raise Exception(f'No input files for dataset {dataset} (dasgoclient returned nothing)')

    attempts = retries + 1
    diagnostic = None
    log_path = None
    for attempt in range(1, attempts + 1):
        returncode, combined = _run_cmsrun(files, file_prefix, maxEvents)
        xsec, event_number = _parse_xsec_output(combined)
        if xsec is not None and event_number is not None:
            print(f'Found xsec {xsec} for {dataset}')
            print(f'Found nevents {event_number} for {dataset}')
            return xsec, event_number

        missing = []
        if xsec is None:
            missing.append('cross section')
        if event_number is None:
            missing.append('number of generated events')

        log_path = _save_failure_log(dataset, attempt, combined)
        diagnostic = _diagnose_cmsrun_failure(dataset, missing, returncode, combined, files, maxEvents)
        print(f'\033[93m  attempt {attempt}/{attempts} failed for {dataset} (exit {returncode}); '
              f'full cmsRun log: {log_path}\033[0m')
        if attempt < attempts:
            print('\033[93m  retrying (transient xrootd/file-open errors are common)...\033[0m')

    raise Exception(f'{diagnostic}\n'
                    f'  failed after {attempts} attempt(s); full log of last attempt: {log_path}')

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
    failures = {}
    for dataset in args.datasets:
        print(f'Processing dataset: {dataset}')
        try:
            files = find_files(dataset)

            print(f'\tFound {len(files)} files for dataset {dataset}')

            print(f'\tProcessing files for dataset: {dataset}')
            xsec, nevents = find_xsec(dataset, files, args.file_prefix, args.maxEvents, args.retries)
            print(f'\tFinished processing files for dataset: {dataset}')
            print()
            xsec_parts = xsec.split(' ')
            xsec_val = float(xsec_parts[0])
            xsec_unc = float(xsec_parts[2])
            rel_unc = xsec_unc / xsec_val if xsec_val != 0 else 0
            print(f'\033[95mDataset: {dataset}\033[0m')
            print(f'\033[92mCross section: {xsec_val} +/- {xsec_unc} (rel_unc: {rel_unc})\nNumber of generated events: {nevents}\033[0m')
            results[dataset] = {"xsec": xsec_val, "nGenEvents": nevents, "abs_unc": xsec_unc, "rel_unc": rel_unc}
        except Exception as e:
            # Soft fail: record the problem and keep going with the other datasets.
            failures[dataset] = str(e)
            print(f'\033[91mFAILED to process dataset: {dataset}\033[0m')
            print(f'\033[91m{e}\033[0m')
            print('\033[91m--- traceback ---\033[0m')
            traceback.print_exc()
            print()
            continue


    # Summary of what succeeded and what failed
    print('\n' + '=' * 70)
    print(f'Processed {len(results)}/{len(args.datasets)} dataset(s) successfully.')
    if failures:
        print(f'\033[91m{len(failures)} dataset(s) failed:\033[0m')
        for dataset, reason in failures.items():
            first_line = reason.splitlines()[0] if reason else 'unknown error'
            print(f'\033[91m  - {dataset}: {first_line}\033[0m')
    print('=' * 70 + '\n')

    if args.output_dir:
        # Check that output dir exists
        if not os.path.exists(args.output_dir):
            os.makedirs(args.output_dir)
        with open(f'{args.output_dir}/xsec.json', 'w') as f:
            json.dump(results, f, indent=4)
    else:
        with open(args.extend_json, 'r') as f:
            xsecs = json.load(f)

        xsecs.update(results)

        with open(args.extend_json, 'w') as f:
            json.dump(xsecs, f, indent=4)

    # Signal to callers/automation that not everything went through, while still
    # having written the successful results above.
    if failures:
        sys.exit(1)

