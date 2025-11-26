import os
import sys
import argparse

def parse_arguments():
    parser = argparse.ArgumentParser(description="Find the files for a given dataset")
    parser.add_argument("--dataset_query", type=str, required=True, help="The dataset query for DAS")
    parser.add_argument("--output_dir", type=str, required=True, help="The output directory")
    parser.add_argument("--combine", action="store_true", help="Combine the datasets' files into one file")
    parser.add_argument("--private", action="store_true", help="Use append instance=prod/phys03 to dataset query")

    args = parser.parse_args()

    return args

def find_das_files(dataset_query: str, output_dir: str, combine_datasets: bool = False, private: bool = False):
    # Query DAS for the datasets
    print(f'/cvmfs/cms.cern.ch/common/dasgoclient --query="dataset dataset={dataset_query}{" instance=prod/phys03 " if private else " "}" > {output_dir}/datasets.txt')
    os.system(f'/cvmfs/cms.cern.ch/common/dasgoclient --query="dataset dataset={dataset_query}{" instance=prod/phys03 " if private else " "}" > {output_dir}/datasets.txt')

    # Read the datasets
    with open(f'{output_dir}/datasets.txt', 'r') as f:
        datasets = f.readlines()

    # Remove the file
    os.system(f'rm {output_dir}/datasets.txt')

    # Remove possible previous dataset files
    for dataset in datasets:
        dataset = dataset.strip()
        dataset_name = dataset.split('/')[1]
        os.system(f'rm {output_dir}/{dataset_name}.txt')

    # For each dataset, find the files
    for dataset in datasets:
        dataset = dataset.strip()
        dataset_name = dataset.split('/')[1]
        print(f'Finding files for {dataset_name}')
        if combine_datasets:
            print(f'/cvmfs/cms.cern.ch/common/dasgoclient --query="file dataset={dataset}{" instance=prod/phys03 " if private else " "}" >> {output_dir}/combined.txt')
            os.system(f'/cvmfs/cms.cern.ch/common/dasgoclient --query="file dataset={dataset}{" instance=prod/phys03 " if private else " "}" >> {output_dir}/combined.txt')
        else:
            print(f'/cvmfs/cms.cern.ch/common/dasgoclient --query="file dataset={dataset}{" instance=prod/phys03 " if private else " "}" >> {output_dir}/{dataset_name}.txt')
            os.system(f'/cvmfs/cms.cern.ch/common/dasgoclient --query="file dataset={dataset}{" instance=prod/phys03 " if private else " "}" >> {output_dir}/{dataset_name}.txt')

if __name__ == '__main__':
    # Get the arguments
    args = parse_arguments()

    dataset_query = args.dataset_query
    output_dir = args.output_dir
    combine_datasets = args.combine
    private = args.private

    # Check if the output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Find the DAS files
    find_das_files(dataset_query, output_dir, combine_datasets, private)