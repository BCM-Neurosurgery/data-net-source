"""
Run any preparation steps required before a source parser can be run
"""

import os
import json
import argparse
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

    # Temp first step, make a simple empty upload log
    log_dir = config['parser']['init']['middle']['path']
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, 'upload_state.json'), 'w') as logfile:
        json.dump(EMPTY_LOG, logfile)



