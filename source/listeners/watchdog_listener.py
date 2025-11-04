import os
import time
import threading
from datetime import datetime
from watchdog.events import (
    FileSystemEventHandler,
    FileClosedEvent,
    FileMovedEvent,
    FileCreatedEvent,
    FileModifiedEvent,
    RegexMatchingEventHandler
)

from source.listeners.base import BaseListener


class PipelineEventHandler(RegexMatchingEventHandler):
    """
    A custom event handler that bridges watchdog and the data-net-source pipeline.
    """
    def __init__(self, parser_instance, **kwargs):
        # Pass all regex arguments to the superclass for filtering.
        super().__init__(**kwargs)
        self.parser = parser_instance
        self.parser.info("RegexMatchingEventHandler initialized. Ready for matched events.")

    def on_created(self, event: FileCreatedEvent):
        """Called when a file or directory is created."""
        self.parser.add_to_batch(event)

    def on_modified(self, event: FileModifiedEvent):
        """Called when a file is modified."""
        self.parser.add_to_batch(event)

    def on_closed(self, event: FileClosedEvent):
        """Called when a file opened for writing is closed."""
        self.parser.add_to_batch(event)

    def on_moved(self, event: FileMovedEvent):
        """Called when a file is moved or renamed."""
        self.parser.add_to_batch(event)


class WatchdogListenerMixin(BaseListener):
    """
    A concrete listener that uses 'watchdog' to monitor a directory and processes
    new files.
    """
    
    @property
    def listener_name(self) -> str:
        """The name of this listener mixin (used by config generator)."""
        return "WatchdogListenerMixin"
    
    @property
    def mixin_module_path(self):
        """Module path for this mixin."""
        return "listeners.watchdog_listener"
    
    @property
    def mixin_description(self):
        """Human-readable description."""
        return "Monitor filesystem for new files in real-time"
    
    @property
    def required_dependencies(self):
        """Required Python packages for this listener."""
        return ['watchdog']
    
    @property
    def config_with_comments(self):
        """Configuration template with inline comments - (value, comment) tuples."""
        return {
            'path': ('path/to/monitor', 'Directory path to monitor for file changes'),
            'include_patterns': (['.*\\.csv$', '.*\\.txt$'], 'List of regex patterns for files to include (e.g., [\'.*\\\\.csv$\', \'.*\\\\.txt$\'])'),
            'exclude_patterns': (['.*\\.tmp$'], 'List of regex patterns for files to exclude (e.g., [\'.*\\\\.tmp$\'])'),
            'batch_max_size': (10, 'Maximum number of files to accumulate before processing'),
            'batch_max_latency_seconds': (60, 'Maximum seconds to wait before processing batch (even if not full)'),
        }

    def create_event_handler(self):
        """Create the RegexMatchingEventHandler for this listener."""
        source_config = self.source_location
        
        # Preparing arguments for the RegexMatchingEventHandler from the config file.
        handler_kwargs = {
            'regexes': source_config.get('include_patterns', ['.*']), # Default to match everything
            'ignore_regexes': source_config.get('exclude_patterns', []),
            'ignore_directories': True, # Using the handler's built-in directory ignoring - helps empty directories
            'case_sensitive': False
        }
        
        return PipelineEventHandler(parser_instance=self, **handler_kwargs)

    def parse_event(self, raw_event: FileSystemEventHandler) -> tuple[str | None, str | None]:
        """
        Parses a watchdog event to extract file paths and filter unwanted files,
        returning a (final_path, old_path) tuple. Path-based filtering is
        handled by the RegexMatchingEventHandler.
        """
        # Ignore all events that are for directories, double checking here.
        if raw_event.is_directory:
            return None, None

        final_path, old_path = None, None
        if isinstance(raw_event, FileMovedEvent):
            final_path = raw_event.dest_path
            old_path = raw_event.src_path
        else:
            final_path = raw_event.src_path

        return final_path, old_path

    def save(self, completed: dict):
        """Saves the state for a completed batch of files."""
        now = datetime.now().timestamp()
        for status, events in completed.items():
            for event in events:
                event['timestamp'] = now

        current_state = self.load_state()
        for key in ['success', 'failure', 'skipped']:
            if key in completed and completed[key]:
                current_state[key].extend(completed[key])
        self.write_state(current_state)

    def clean(self):
        """Performs state file cleanup after a batch is processed."""
        current_state = self.load_state()
        deduplicated_state = self.clean_outdated(current_state)
        final_state = self.clean_old_success(deduplicated_state)
        self.write_state(final_state)