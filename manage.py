"""
Helper script to manage the parser, with a focus on the saved state of the parser

Currently implemented options:
"""
import json
import argparse
import os.path

from run import load_config, load_parser


def iter_saved(config, success=True, failure=True, after=0, before=float('inf')):

    all_events = []
    state_file = os.path.join(config['parser']['init']['state_path'], 'upload_state.json')
    with open(state_file) as state_json:
        state_data = json.load(state_json)

    if success:
        all_events.extend(state_data['success'])
    if failure:
        all_events.extend(state_data['failure'])

    for event in all_events:
        if after < event['timestamp'] < before:
            yield event


def count(config, **kwargs):
    """Print the number of matching events"""
    num = 0
    for i in iter_saved(config, **kwargs):
        num += 1
    print(f'Found {num} saved events')


def forget(config, **kwargs):
    """Remove all matching events from the saved state"""
    pass


if __name__ == '__main__':

    parser = argparse.ArgumentParser()

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        'command',
        type=str,
        choices=['count', 'forget'],
        help='The management sub command to run for this parser'
    )
    arg_parser.add_argument(
        'config_file',
        type=str,
        help='Path to the config file that specifies the parser to run'
    )
    arg_parser.add_argument(
        '--after',
        action='store',
        type=int,
        help='Only events with a timestamp after this time will be included'
    )
    arg_parser.add_argument(
        '--before',
        action='store',
        type=int,
        help='Only events with a timestamp before this time will be included'
    )
    args = arg_parser.parse_args()

    config_json = load_config(args.config_file)

    # Parse all the filtering/selection arguments into a dict
    filter_kwargs = {}
    if args.after is not None:
        filter_kwargs['after'] = args.after
    if args.before is not None:
        filter_kwargs['before'] = args.before

    if args.command == 'count':
        count(config_json, **filter_kwargs)

    elif args.command == 'forget':
        forget(config_json, **filter_kwargs)