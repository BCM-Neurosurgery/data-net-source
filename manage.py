"""
Helper script to manage the parser, with a focus on the saved state of the parser
Intended to be used as a command-line tool. See the help message (`python manage.py -h`) for full details

All events are treated individually, and are only included in the processing for the given sub-command if they match
all the criteria specified as options to this script

Currently implemented sub-commands:
  - count: count the total number of matching events
  - time-range: return the earliest and latest timestamp of the matching events
  - forget: remove the matching events from the state file

If the sub-command makes changes to the state file, this tool will ask for confirmation before over-writing
"""
import copy
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
        upload = bool(re.search(upload_match, event['uploaded']))
    else:
        upload = True

    return in_time and upload


def iter_saved(config, success=True, failure=True, skipped=True, **kwargs):
    """
    Generator that yields a tuple for each event matching all the given conditions

    Tuple has two elements, first is the event category (i.e. success or failure) and the second is the dictionary
        containing all the event details.

    :param config: Config file for the parser we're working with. Must specify the state path to find the state file
    :param success: If true, the list of 'success' events will be included in the iteration
    :param failure: If true, the list of 'failure' events will be included in the iteration
    :param skipped: If true, the list of 'skipped' events will be included in the iteration
    :param kwargs: Additional search condition key word arguments, passed to match_event()
    """
    all_events = []
    state_file = os.path.join(config['parser']['init']['state_path'], 'upload_state.json')
    with open(state_file) as state_json:
        state_data = json.load(state_json)

    if success:
        all_events.extend(event_tuples('success', state_data))
    if failure:
        all_events.extend(event_tuples('failure', state_data))
    if skipped:
        all_events.extend(event_tuples('skipped', state_data))

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
    """Print the earliest and latest time of all matching events"""
    times = []
    for c, event in iter_saved(config, **kwargs):
        times.append(event['timestamp'])
    if len(times):
        print(f'Found events in time range: [{min(times)} - {max(times)}]')
    else:
        print(f'Found no events matching the given criteria!')


def forget(config, success=False, failure=False, skipped=False, **kwargs):
    """Remove all matching events from the saved state"""

    remembered = []
    forgetting = []
    for category, event in iter_saved(config):

        is_category = ((success and category == 'success')
                       or (failure and category == 'failure')
                       or (skipped and category == 'skipped'))
        matches = is_category and match_event(event, **kwargs)

        # Only remember the events that do not match the forget selection
        if matches:
            forgetting.append((category, event))
        else:
            remembered.append((category, event))

    print(f'Search completed.')
    print(f'Found {len(forgetting)} matching events to forget')

    decide_action(config, remembered)


def move(config, success=False, failure=False, skipped=False, **kwargs):

    # Build up a base dictionary of unaffected events, by collecting all events that are not in one of the categories
    # that events to be moved will be sourced from
    print('Loading unaffected events... ')
    unaffected = iter_saved(config, success=(not success), failure=(not failure), skipped=(not skipped))
    base = list(unaffected)

    print('Searching for events to move... ')
    potential = iter_saved(config, success=success, failure=failure, skipped=skipped)
    to_move = []
    for cat, event in potential:
        if match_event(event, **kwargs):
            to_move.append(event)
        else:
            base.append((cat, event))

    print(f'Found {len(to_move)} matching events to move')
    if len(to_move) == 0:
        print('No events to move! Exiting...')
        exit(0)
    target = get_input(
        {
            'success': 'Show the new state without saving',
            'skipped': 'Save these changes directly to the primary state file',
            'failure': 'Save changes to primary file, but cache the old state file'
        },
        'Where would you like to move these ?\n'
    )
    print(f'Moving {len(to_move)} events to {target}...')
    for event in to_move:
        base.append((target, event))

    decide_action(config, base)


def clean(config, success=False, failure=False, skipped=False, **kwargs):
    """Apply any of the library of cleaning functions defined for the parser"""
    import inspect

    # Load the source parser and find all available cleaning functions
    source_parser = load_parser(config['parser'])
    if 'logging' in config:
        source_parser.make_loggers(config['logging'])
    methods = inspect.getmembers(source_parser, predicate=inspect.ismethod)
    cleaners = {name: func for name, func in methods if name.startswith('clean_')}

    options = {name: func.__doc__ for name, func in cleaners.items()}
    cleaner_name = get_input(options, 'Which cleaning function would you like to run?\n')

    state = source_parser.load_state()
    cleaned = cleaners[cleaner_name](state)

    ready = []
    for category in cleaned.keys():
        ready.extend(event_tuples(category, cleaned))

    decide_action(config, ready)

def format_state_data(events):
    """Re-organize a list of event tuples back into the state dictionary format"""
    state_data = {'success': [], 'failure': [], 'skipped': []}
    for category, event in events:
        state_data[category].append(event)
    return state_data

def decide_action(config, new_events):
    """
    Give the user a chance to verify changes and safely save them to the state file

    :param config: configuration information for the parser we are working with
    :param new_events: List of tuples of all the new events that should be saved
    """
    state_data = format_state_data(new_events)
    print(f'New state file will have {len(new_events)} events with:\n'
          f'  - {len(state_data["success"])} successes\n'
          f'  - {len(state_data["failure"])} failures\n'
          f'  - {len(state_data["skipped"])} skips')

    choice = get_input(
        {
            'show': 'Show the new state without saving',
            'write': 'Save these changes directly to the primary state file',
            'stash': 'Save changes to primary file, but cache the old state file',
            'new': 'Save the changes to a new file',
            'exit': 'Exit without making any changes',
        },
        'Would you like to save these changes?\n'
    )

    state_path = config['parser']['init']['state_path']
    if choice == 'show':
        print(f'The new state file contents will be:')
        print(json.dumps(state_data, indent=2))
        decide_action(config, state_data)
    elif choice == 'write':
        print('Saving to primary file...')
        state_filepath = os.path.join(state_path, 'upload_state.json')
        with open(state_filepath, 'w') as state_file:
            json.dump(state_data, state_file)
        print(f'Saved to {state_filepath}')
    elif choice == 'new':
        print(f'Saving to new file...')
        base = 'new_upload_state'
        n_new = 1 + len(list(filter(lambda f: (base in f), os.listdir(state_path))))
        new_state_filepath = os.path.join(state_path, f'{base}_{n_new}.json')
        with open(new_state_filepath, 'w') as state_file:
            json.dump(state_data, state_file)
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
            json.dump(state_data, state_file)
        print(f'Saved to {default_state_path}')
    else:
        print('Exiting without making any changes')


if __name__ == '__main__':

    parser = argparse.ArgumentParser()

    arg_parser = argparse.ArgumentParser(
        description="""
        Command Line Helper script for easier management of the state file for a specific data net source parser.
        
        All events are treated individually, and are only included in the processing for the given sub-command if they 
        match all the criteria specified as options to this script. See the -- options for possible criteria
        """
    )
    arg_parser.add_argument(
        'config_file',
        type=str,
        help='Path to the config file that specifies the parser whose state file we are using'
    )
    arg_parser.add_argument(
        'command',
        type=str,
        choices=['count', 'forget', 'time-range', 'move', 'clean'],
        help='The management sub command to run for this parser'
    )
    arg_parser.add_argument(
        '--after',
        action='store',
        type=int,
        metavar='TIMESTAMP',
        help='Only events with a timestamp after this time will be included'
    )
    arg_parser.add_argument(
        '--before',
        action='store',
        type=int,
        metavar='TIMESTAMP',
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
        '--skipped',
        action='store_true',
        help='Include skipped events in the search'
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
        metavar='REGEX',
        help='Filter events by upload path based on the given regex'
    )
    args = arg_parser.parse_args()

    config_json = load_config(args.config_file)

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
    filter_kwargs['skipped'] = args.skipped
    if args.all_events:
        filter_kwargs['success'] = True
        filter_kwargs['failure'] = True
        filter_kwargs['skipped'] = True

    # Send processing off to the appropriate function based on the command given
    if args.command == 'count':
        count(config_json, **filter_kwargs)
    elif args.command == 'time-range':
        get_time_range(config_json, **filter_kwargs)
    elif args.command == 'forget':
        forget(config_json, **filter_kwargs)
    elif args.command == 'move':
        move(config_json, **filter_kwargs)
    elif args.command == 'clean':
        clean(config_json, **filter_kwargs)
    else:
        raise KeyError(f'Unrecognized command: {args.command}')