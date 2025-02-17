"""
Run any preparation steps required before a source parser can be run
"""

import os
import json
import argparse
import subprocess
import sys
from run import load_config, load_parser


EMPTY_LOG = {
    "success": [],
    "failure": []
}


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('config_file', type=str,
                            help='Path to the config file that specifies the parser to run')
    args = arg_parser.parse_args()

    config = load_config(args.config_file)
    # parser = load_parser(config)
    # parser.prepare()

    # Install the dependencies of this specific module (currently we only support pip dependencies)
    if 'dependencies' in config and 'pip' in config['dependencies']:
        for package in config['dependencies']['pip']:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    else:
        print('No compatible dependencies found. Skipping')

    # Temp first step, make a simple empty upload log
    log_dir = config['parser']['init']['state_path']
    os.makedirs(log_dir, exist_ok=True)
    state_filepath = os.path.join(log_dir, 'upload_state.json')

    # Only make a new state file if none exists
    if not os.path.exists(state_filepath):
        print('Making an empty upload state file')
        with open(state_filepath, 'w') as statefile:
            json.dump(EMPTY_LOG, statefile)

    print('Done.')



