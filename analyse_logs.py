"""
Helper script to analyze parser log files (upload_log.txt)
Intended to be used as a command-line tool. See the help message (`python analyse_logs.py -help`) for full details

Currently implemented sub-commands:
  - logs: display log entries (use --levels to filter by level, --brief for first line only, --count to show counts only)
  - search: search for specific patterns in the log files (case-insensitive, use --count to show match count only)
  - tail: show the last N lines of the most recent log file
  - run-details: show detailed breakdown of a specific run
  - file-history: show history of a specific file (use --filename parameter, --count to show mention count only)
"""
import argparse
import os.path
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime
from collections import defaultdict, Counter
from run import load_config


class LogEntry:
    """Represents a single log entry from the log file"""
    
    def __init__(self, timestamp, level, message):
        self.timestamp = timestamp
        self.level = level
        self.message = message
        self.datetime = None
        
        # Parse the timestamp string to datetime
        try:
            self.datetime = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass
    
    def __repr__(self):
        return f"<LogEntry {self.timestamp} {self.level}: {self.message[:50]}...>"
    
    def matches(self, pattern):
        """Check if the log entry matches a regex pattern (case-insensitive)"""
        return bool(re.search(pattern, self.message, re.IGNORECASE))


def parse_log_file(filepath):
    """
    Parse a log file and yield LogEntry objects
    
    :param filepath: Path to the log file to parse
    :yields: LogEntry objects for each parsed log line
    """
    # Standard log format: YYYY-MM-DD HH:MM:SS LEVEL    MESSAGE
    log_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)$')
    
    if not os.path.exists(filepath):
        print(f'Warning: Log file not found: {filepath}')
        return
    
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        current_entry = None
        
        for line in f:
            line = line.rstrip('\n')
            match = log_pattern.match(line)
            
            if match:
                # This is a new log entry
                if current_entry:
                    yield current_entry
                
                timestamp, level, message = match.groups()
                current_entry = LogEntry(timestamp, level, message)
            else:
                # This is a continuation of the previous log entry (e.g., traceback)
                if current_entry:
                    current_entry.message += '\n' + line
        
        # Don't forget the last entry
        if current_entry:
            yield current_entry


def get_log_files(config):
    """
    Get all log files for this parser (including rotated backups)
    
    :param config: Config dictionary for the parser
    :returns: List of log file paths, ordered from newest to oldest
    """
    log_files = []
    
    if 'logging' not in config or 'file' not in config['logging']:
        print('Warning: No file logging configured for this parser')
        return log_files
    
    log_config = config['logging']['file']
    state_path = config['parser']['init']['state_path']
    
    # Determine the main log file path
    if 'filepath' in log_config:
        main_log = log_config['filepath']
    elif 'filename' in log_config:
        main_log = os.path.join(state_path, log_config['filename'])
    else:
        main_log = os.path.join(state_path, 'upload_log.txt')
    
    # Add the main log file
    if os.path.exists(main_log):
        log_files.append(main_log)
    
    # Find rotated backup files (upload_log.txt.1, upload_log.txt.2, etc.)
    max_files = log_config.get('max_files', 5)
    for i in range(1, max_files + 1):
        backup_log = f'{main_log}.{i}'
        if os.path.exists(backup_log):
            log_files.append(backup_log)
    
    return log_files


def iter_logs(config, log_files=None, after=None, before=None, level_filter=None):
    """
    Generator that yields LogEntry objects from all log files matching the given criteria
    
    :param config: Config dictionary for the parser
    :param log_files: Optional list of specific log files to read. If None, reads all log files
    :param after: Optional datetime object - only yield entries after this time
    :param before: Optional datetime object - only yield entries before this time
    :param level_filter: Optional list of log levels to include (e.g., ['ERROR', 'WARNING'])
    :yields: LogEntry objects matching the criteria
    """
    if log_files is None:
        log_files = get_log_files(config)
    
    for log_file in log_files:
        for entry in parse_log_file(log_file):
            # Apply time filters
            if after and entry.datetime and entry.datetime < after:
                continue
            if before and entry.datetime and entry.datetime > before:
                continue
            
            # Apply level filter
            if level_filter and entry.level not in level_filter:
                continue
            
            yield entry


def _resolve_pager_command(pager_mode):
    """Resolve pager command based on mode and terminal context."""
    if pager_mode == 'off':
        return None

    if shutil.which('less'):
        return ['less', '-R']

    return None


@contextmanager
def maybe_page_stdout(pager_mode='less'):
    """Route stdout to a pager process when configured and available."""
    pager_cmd = _resolve_pager_command(pager_mode)
    if not pager_cmd:
        if pager_mode == 'less':
            print(f'Warning: Requested pager "{pager_mode}" is not available; writing directly to stdout.', file=sys.stderr)
        yield
        return

    pager_process = subprocess.Popen(
        pager_cmd,
        stdin=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    original_stdout = sys.stdout

    try:
        sys.stdout = pager_process.stdin
        yield
    except BrokenPipeError:
        # User quit the pager early.
        pass
    finally:
        sys.stdout = original_stdout
        if pager_process.stdin and not pager_process.stdin.closed:
            try:
                pager_process.stdin.close()
            except BrokenPipeError:
                pass
        pager_process.wait()


def logs(config, brief=False, show_count=False, **kwargs):
    """Display log entries (filtered by --levels if specified)"""
    # Require at least one filter to prevent displaying massive logs (unless just counting)
    has_time_filter = 'after' in kwargs or 'before' in kwargs
    has_level_filter = 'level_filter' in kwargs and kwargs['level_filter'] is not None
    
    if not show_count and not has_time_filter and not has_level_filter:
        print('Error: The logs command requires at least one filter to prevent displaying massive amounts of data.')
        print('Please use --after, --before, or --levels to filter the log entries.')
        print('\nExamples:')
        print('  python analyse_logs.py config.toml logs --levels ERROR')
        print('  python analyse_logs.py config.toml logs --after 2025-12-01')
        print('  python analyse_logs.py config.toml logs --after 2025-12-01 --before 2025-12-10')
        print('  python analyse_logs.py config.toml logs --count  # Show counts by level')
        return
    
    # If --count is specified, show counts by level
    if show_count:
        level_counts = Counter()
        total = 0
        for entry in iter_logs(config, **kwargs):
            level_counts[entry.level] += 1
            total += 1
        
        print(f'Found {total} log entries:')
        for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            if level in level_counts:
                print(f'  {level:10s}: {level_counts[level]:6d}')
        return
    
    # Stream full log entries to avoid loading huge logs into memory
    levels = kwargs.get('level_filter')
    if levels:
        level_str = ', '.join(levels)
        print(f'Streaming log entries with levels: {level_str}\n')
    else:
        print('Streaming log entries:\n')

    total = 0
    for i, entry in enumerate(iter_logs(config, **kwargs), 1):
        total = i
        print(f'--- Entry #{i} [{entry.timestamp} {entry.level}] ---')
        if brief:
            # Just show first line
            first_line = entry.message.split('\n')[0]
            print(first_line)
        else:
            print(entry.message)
        print()

    if total == 0:
        print('No log entries found matching the given criteria.')
    else:
        print(f'Displayed {total} log entries.')


def search(config, pattern, show_count=False, **kwargs):
    """Search for a pattern in the log files and display matching entries (case-insensitive)"""
    if show_count:
        count = 0
        for entry in iter_logs(config, **kwargs):
            if entry.matches(pattern):
                count += 1
        print(f'Found {count} matching entries for pattern: "{pattern}"')
        return

    print(f'Searching for pattern: "{pattern}"\n')
    match_count = 0
    for entry in iter_logs(config, **kwargs):
        if not entry.matches(pattern):
            continue

        match_count += 1
        i = match_count
        print(f'--- Match #{i} [{entry.timestamp} {entry.level}] ---')
        print(entry.message)
        print()

    if match_count == 0:
        print(f'No matching entries found for pattern: "{pattern}"')
    else:
        print(f'Found {match_count} matching entries for pattern: "{pattern}"')


def tail(config, n=50, **kwargs):
    """Show the last N lines of the most recent log file"""
    log_files = get_log_files(config)
    
    if not log_files:
        print('No log files found!')
        return
    
    # Get the most recent log file
    most_recent = log_files[0]
    print(f'Showing last {n} lines from: {most_recent}\n')
    
    entries = list(parse_log_file(most_recent))
    
    if not entries:
        print('No log entries found!')
        return
    
    # Show last N entries
    for entry in entries[-n:]:
        print(f'{entry.timestamp} {entry.level:8s} {entry.message}')


def run_details(config, run_number=None, **kwargs):
    """Show detailed breakdown of a specific run by number"""
    runs = []
    current_run = None
    all_entries = []
    
    for entry in iter_logs(config, **kwargs):
        if 'STARTING PARSER' in entry.message:
            # Start of a new run
            if current_run:
                runs.append(current_run)
            current_run = {
                'start_time': entry.datetime,
                'start_entry': entry,
                'end_time': None,
                'exit_code': None,
                'entries': [entry]
            }
        elif current_run:
            current_run['entries'].append(entry)
            
            if 'FINISHED with status code' in entry.message:
                match = re.search(r'status code \((\d+)\)', entry.message)
                if match:
                    current_run['exit_code'] = int(match.group(1))
                current_run['end_time'] = entry.datetime
    
    # Don't forget the last run
    if current_run:
        runs.append(current_run)
    
    if not runs:
        print('No parser runs found in logs.')
        return
    
    # If no run number specified, show list of available runs
    if run_number is None:
        print(f'Found {len(runs)} parser runs. Use --run NUMBER to see details.\n')
        print('Available runs:')
        for i, run in enumerate(runs, 1):
            status = '✓' if run['exit_code'] == 0 else '✗' if run['exit_code'] else '?'
            duration = ''
            if run['start_time'] and run['end_time']:
                delta = run['end_time'] - run['start_time']
                duration = f' ({delta})'
            print(f'  Run #{i:3d} {status} [{run["start_time"]}]{duration} - {len(run["entries"])} log entries')
        return
    
    # Show details for specific run
    if run_number < 1 or run_number > len(runs):
        print(f'Error: Run #{run_number} not found. Available runs: 1-{len(runs)}')
        return
    
    run = runs[run_number - 1]
    
    print(f'=== Run #{run_number} Details ===\n')
    print(f'Start Time: {run["start_time"]}')
    if run['end_time']:
        print(f'End Time:   {run["end_time"]}')
        duration = run['end_time'] - run['start_time']
        print(f'Duration:   {duration}')
    print(f'Exit Code:  {run["exit_code"] if run["exit_code"] is not None else "incomplete"}')
    print(f'Log Entries: {len(run["entries"])}\n')
    
    # Count by level
    level_counts = Counter(e.level for e in run['entries'])
    print('Entries by level:')
    for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
        if level in level_counts:
            print(f'  {level}: {level_counts[level]}')
    print()
    
    # Show all entries
    print('All log entries for this run:')
    print('-' * 80)
    for entry in run['entries']:
        print(f'{entry.timestamp} {entry.level:8s} {entry.message}')
        print()


def file_history(config, filename, show_count=False, **kwargs):
    """Show history of a specific file in the logs"""
    if not filename:
        print('Error: --filename parameter is required for file-history command')
        return
    
    if show_count:
        count = 0
        for entry in iter_logs(config, **kwargs):
            if filename.lower() in entry.message.lower():
                count += 1
        print(f'Found {count} log entries mentioning "{filename}"')
        return

    print(f'Searching for entries mentioning "{filename}":\n')
    match_count = 0
    for entry in iter_logs(config, **kwargs):
        if filename.lower() not in entry.message.lower():
            continue

        match_count += 1
        i = match_count
        print(f'--- Entry #{i} [{entry.timestamp} {entry.level}] ---')
        # Highlight the filename in the message
        print(entry.message)
        print()

    if match_count == 0:
        print(f'No log entries found mentioning file: "{filename}"')
    else:
        print(f'Found {match_count} log entries mentioning "{filename}"')


def parse_datetime(date_str):
    """Parse a datetime string in various formats"""
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
        '%Y%m%d',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    raise ValueError(f'Unable to parse datetime: {date_str}')


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser(
        description="""
        Command Line Helper script for analyzing the text log files for a specific data net source parser.
        
        This script analyzes the upload_log.txt file and its rotated backups created by the Python logging system.
        For analyzing the upload_state.json file, use manage.py instead.
        """
    )
    
    arg_parser.add_argument(
        'config_file',
        type=str,
        help='Path to the config file that specifies the parser whose log files we are analyzing'
    )
    
    arg_parser.add_argument(
        'command',
        type=str,
        choices=['logs', 'search', 'tail', 'run-details', 'file-history'],
        help='The analysis sub-command to run'
    )
    
    # Filtering arguments
    arg_parser.add_argument(
        '--after',
        action='store',
        type=str,
        metavar='DATETIME',
        help='Only include log entries after this time (format: YYYY-MM-DD HH:MM:SS or YYYY-MM-DD)'
    )
    
    arg_parser.add_argument(
        '--before',
        action='store',
        type=str,
        metavar='DATETIME',
        help='Only include log entries before this time (format: YYYY-MM-DD HH:MM:SS or YYYY-MM-DD)'
    )
    
    arg_parser.add_argument(
        '--levels',
        action='store',
        type=str,
        nargs='+',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Only include log entries with these levels'
    )
    
    # Command-specific arguments
    arg_parser.add_argument(
        '--pattern',
        action='store',
        type=str,
        help='Regex pattern to search for (case-insensitive). Examples: "upload", "error.*failed", "Found [0-9]+ tasks"'
    )
    
    arg_parser.add_argument(
        '--brief',
        action='store_true',
        help='For logs command, only show first line of each message (not full traceback/details)'
    )
    
    arg_parser.add_argument(
        '--count',
        action='store_true',
        help='Show counts only instead of full entries (works with logs, search, file-history commands)'
    )
    
    arg_parser.add_argument(
        '--lines',
        action='store',
        type=int,
        default=50,
        metavar='N',
        help='Number of lines to show (used with tail command, default: 50)'
    )
    
    arg_parser.add_argument(
        '--run',
        action='store',
        type=int,
        metavar='NUMBER',
        help='Run number to show details for (used with run-details command)'
    )
    
    arg_parser.add_argument(
        '--filename',
        action='store',
        type=str,
        metavar='NAME',
        help='Filename to search for (used with file-history command)'
    )

    arg_parser.add_argument(
        '--pager',
        action='store',
        type=str,
        choices=['less', 'off'],
        default='less',
        help='Pager mode for long output: less (default) or off'
    )
    
    args = arg_parser.parse_args()
    
    # Load the config
    config = load_config(args.config_file)
    
    # Parse time filters
    filter_kwargs = {}
    if args.after:
        filter_kwargs['after'] = parse_datetime(args.after)
    if args.before:
        filter_kwargs['before'] = parse_datetime(args.before)
    if args.levels:
        filter_kwargs['level_filter'] = args.levels
    
    commands_with_pager = {'logs', 'search', 'run-details', 'file-history'}
    pager_mode = args.pager
    if args.command not in commands_with_pager or args.count:
        pager_mode = 'off'

    # Execute the appropriate command
    with maybe_page_stdout(pager_mode):
        if args.command == 'logs':
            logs(config, brief=args.brief, show_count=args.count, **filter_kwargs)

        elif args.command == 'search':
            if not args.pattern:
                print('Error: --pattern is required for search command')
                exit(1)
            search(config, args.pattern, show_count=args.count, **filter_kwargs)

        elif args.command == 'tail':
            tail(config, n=args.lines, **filter_kwargs)

        elif args.command == 'run-details':
            run_details(config, run_number=args.run, **filter_kwargs)

        elif args.command == 'file-history':
            if not args.filename:
                print('Error: --filename is required for file-history command')
                exit(1)
            file_history(config, filename=args.filename, show_count=args.count, **filter_kwargs)

        else:
            raise KeyError(f'Unrecognized command: {args.command}')
