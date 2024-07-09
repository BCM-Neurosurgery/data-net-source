"""
Helper script to manage the parser, with a focus on the saved state of the parser

Currently implemented options:
"""
import json
import argparse
import os.path
import re
import shutil

from run import load_config, load_parser


def get_input(options, instructions=None):
    """Recursive function to stubbornly force user to enter one of the possible options"""
    if instructions is None:
        instructions = f"""
        Please enter one of these options or type 'help' for more details
        """
    print(instructions + f"{', '.join(options.keys())}")

    response = input("> ")
    if response == '?' or response == 'help':
        help_message = 'The available options are:'
        for option, description in options.items():
            help_message += f"'{option}': {description}\n"
        print(help_message)
    if response in options:
        return response
    else:
        return get_input(options, instructions)


def event_tuples(event_category, state_data):
    """Extract all the events in a category as a list of tuples labeling the category"""
    n_events = len(state_data[event_category])
    labels = [event_category] * n_events
    return list(zip(labels, state_data[event_category]))


def match_event(event, after=0, before=float('inf'), upload_match=None):
    """Check if an event matches all the given conditions"""
    in_time = after < event['timestamp'] < before
    if upload_match:
        upload = bool(re.match(upload_match, event['uploaded']))
    else:
        upload = True

    return in_time and upload


def iter_saved(config, success=True, failure=True, **kwargs):

    all_events = []
    state_file = os.path.join(config['parser']['init']['state_path'], 'upload_state.json')
    with open(state_file) as state_json:
        state_data = json.load(state_json)

    if success:
        all_events.extend(event_tuples('success', state_data))
    if failure:
        all_events.extend(event_tuples('failure', state_data))

    for category, event in all_events:
        if match_event(event, **kwargs):
            yield category, event


def count(config, **kwargs):
    """Print the number of matching events"""
    num = 0
    for i in iter_saved(config, **kwargs):
        num += 1
    print(f'Found {num} saved events')


def get_time_range(config, **kwargs):
    """Print the time of all events"""
    times = []
    for c, event in iter_saved(config, **kwargs):
        times.append(event['timestamp'])
    if len(times):
        print(f'Found events in time range: [{min(times)} - {max(times)}]')
    else:
        print(f'Found no events matching the given criteria!')


def forget(config, success=False, failure=False, **kwargs):
    """Remove all matching events from the saved state"""

    remembered = {}
    forgetting = {}
    for category, event in iter_saved(config):

        category = (success and category == 'success') or (failure and category == 'failure')
        matches = category and match_event(event, **kwargs)

        # Only remember the events that do not match the forget selection
        if matches:
            forgetting.setdefault(category, []).append(event)
        else:
            remembered.setdefault(category, []).append(event)

    print(f'Search completed.')
    print(f'Found {len(forgetting)} matching events to forget')

    decide_action(config, remembered)


def decide_action(config, new_events):

    choice = get_input(
        {
            'show': 'Show changes without saving',
            'write': 'Save these changes directly to the primary state file',
            'stash': 'Save changes to primary file, but cache the old state file',
            'new': 'Save the changes to a new file',
            'exit': 'Exit without making any changes',
        },
        'Would you like to save these changes?\n'
    )

    state_path = config['parser']['init']['state_path']
    if choice == 'show':
        print(json.dumps(new_events, indent=2))
        decide_action(config, new_events)
    elif choice == 'yes':
        print('Saving to primary file...')
        state_filepath = os.path.join(state_path, 'upload_state.json')
        with open(state_filepath, 'w') as state_file:
            json.dump(new_events, state_file)
        print(f'Saved to {state_filepath}')
    elif choice == 'new':
        print(f'Saving to new file...')
        base = 'new_upload_state'
        n_new = 1 + len(list(filter(lambda f: (base in f), os.listdir(state_path))))
        new_state_filepath = os.path.join(state_path, f'{base}_{n_new}.json')
        with open(new_state_filepath, 'w') as state_file:
            json.dump(new_events, state_file)
        print(f'Saved to {new_state_filepath}')
    elif choice == 'stash':
        print(f'Caching old state file before saving...')
        default_state_path = os.path.join(state_path, 'upload_state.json')
        base = 'old_upload_state'
        n_old = 1 + len(list(filter(lambda f: (base in f), os.listdir(state_path))))
        old_state_filepath = os.path.join(state_path, f'{base}_{n_old}.json')
        shutil.copyfile(default_state_path, old_state_filepath)
        print(f'Cached old state to {old_state_filepath}')
        with open(default_state_path, 'w') as state_file:
            json.dump(new_events, state_file)
        print(f'Saved to {default_state_path}')
    else:
        print('Exiting without making any changes')


if __name__ == '__main__':

    parser = argparse.ArgumentParser()

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        'command',
        type=str,
        choices=['count', 'forget', 'time-range'],
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
    arg_parser.add_argument(
        '--success',
        action='store_true',
        help='Include failure events in the search'
    )
    arg_parser.add_argument(
        '--failure',
        action='store_true',
        help='Include failure events in the search'
    )
    arg_parser.add_argument(
        '--all-events',
        action='store_true',
        help='Include all events in the search'
    )
    arg_parser.add_argument(
        '--upload-match',
        action='store',
        type=str,
        help='Filter events by upload path based on the given regex'
    )
    args = arg_parser.parse_args()

    config_json = load_config(args.config_file)

    print(f'Regex: <{args.upload_match}>')

    # Parse all the filtering/selection arguments into a dict
    filter_kwargs = {}
    if args.after is not None:
        filter_kwargs['after'] = args.after
    if args.before is not None:
        filter_kwargs['before'] = args.before
    if args.upload_match is not None:
        filter_kwargs['upload_match'] = args.upload_match

    # Only include successes/failures if all-events or the relevant flag is set to true
    filter_kwargs['success'] = args.success
    filter_kwargs['failure'] = args.failure
    if args.all_events:
        filter_kwargs['success'] = True
        filter_kwargs['failure'] = True

    # Send processing off to the appropriate function based on the command given
    if args.command == 'count':
        count(config_json, **filter_kwargs)
    elif args.command == 'time-range':
        get_time_range(config_json, **filter_kwargs)
    elif args.command == 'forget':
        forget(config_json, **filter_kwargs)