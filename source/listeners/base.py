import time
import threading
import copy
import os
import json
from datetime import datetime
from abc import ABC, abstractmethod
from typing import List, Dict

from watchdog.observers import Observer
from source.common import EMPTY_LOG


class BaseListener(ABC):
    """
    Abstract base class for all listener mixins.

    This class provides event-driven data processing capabilities with batching,
    threading, and state management. Listener mixins should be combined with
    ParserCommon through dynamic class composition, similar to BaseChecker.
    
    All concrete listener mixins MUST implement:
        - required_dependencies: List[str] - Python packages needed
        - config_template: Dict - Example configuration structure
    """
    state_filename = 'upload_state.json'

    # -------------------------------------------------------------------------
    # --- Abstract properties for metadata (required for config generator) ---
    # -------------------------------------------------------------------------

    @property
    @abstractmethod
    def mixin_module_path(self) -> str:
        """
        The module path where this mixin is defined.
        
        :return: Module path relative to 'source' (e.g., 'listeners.watchdog_listener')
        """
        pass

    @property
    @abstractmethod
    def mixin_description(self) -> str:
        """
        Human-readable description of what this listener does.
        
        :return: Description string for config generator
        """
        pass

    @property
    @abstractmethod
    def required_dependencies(self) -> List[str]:
        """
        List of Python packages required by this listener.
        
        :return: List of package names (e.g., ['watchdog', 'requests'])
        """
        pass

    @property
    @abstractmethod
    def config_with_comments(self) -> Dict[str, tuple]:
        """
        Configuration template with inline comments.
        
        Each key maps to a tuple of (value, comment) where:
        - value: The default/example value for this config field
        - comment: Description of what the field does
        
        Example:
            {
                'path': ('path/to/monitor', 'Directory to monitor'),
                'batch_size': (10, 'Number of files per batch')
            }
        
        :return: Dictionary mapping config keys to (value, comment) tuples
        """
        pass

    # -------------------------------------------------------------------------
    # --- Abstract methods to be implemented by concrete listeners ---
    # -------------------------------------------------------------------------

    @property
    @abstractmethod
    def listener_name(self) -> str:
        """
        A simple attribute naming the mixin class for later reference.
        Also used by config generator as the class name.
        """
        pass

    @abstractmethod
    def parse_event(self, raw_event: any) -> tuple[str | None, str | None]:
        """
        Parse a raw event from the source to extract file paths.

        This method translates a source-specific event object into file paths
        that can be processed by the batch system.

        :param raw_event: The native event object from the source (e.g., a
                          watchdog event, a message from a queue).
        :return: A tuple of (final_path, old_path). For simple events, old_path 
                 should be None. For move events, both paths should be provided.
                 Return (None, None) to indicate the event should be skipped.
        """
        pass

    @abstractmethod
    def save(self, completed: dict):
        """
        Save the state of processed files.

        :param completed: A dict with 'success', 'failure', and 'skipped' lists.
        """
        pass

    @abstractmethod
    def clean(self):
        """Perform cleanup actions, like removing old files or consolidating state entries."""
        pass

    @abstractmethod
    def create_event_handler(self):
        """
        Create the specific event handler for this listener type.
        
        :return: Event handler instance compatible with watchdog Observer
        """
        pass

    # -------------------------------------------------------------------------
    # --- Concrete methods providing Observer management ---
    # -------------------------------------------------------------------------

    def setup_observer(self):
        """Initialize the watchdog observer and common configuration."""
        self.observer = Observer()
        source_config = self.source_location
        self.watch_path = source_config.get('path')
        if not self.watch_path:
            raise ValueError("[parser.init.source] must contain a 'path' key.")
        
        self.recursive = source_config.get('recursive', True)
        self.info(f"Observer setup for path: {self.watch_path}, recursive: {self.recursive}")

    def start_observer(self):
        """Start the watchdog observer with the event handler."""
        if not hasattr(self, 'observer') or not self.observer:
            self.setup_observer()

        event_handler = self.create_event_handler()
        self.observer.schedule(event_handler, self.watch_path, recursive=self.recursive)
        self.observer.start()
        self.info(f"Started {self.listener_name} observer on {self.watch_path}")

    def stop_observer(self):
        """Stop and join the watchdog observer."""
        if hasattr(self, 'observer') and self.observer:
            self.observer.stop()
            self.observer.join()
            self.info(f"Stopped {self.listener_name} observer")

    def run_observer_loop(self):
        """Run the main observer loop. Cleanup is handled by ParserCommon.listen()."""
        while True:
            time.sleep(1)

    # -------------------------------------------------------------------------
    # --- Concrete methods providing the batching functionality ---
    # -------------------------------------------------------------------------

    def setup_batching(self):
        """Initializes all common batching attributes from the configuration."""
        source_config = self.source_location
        self._batch_max_size = source_config.get('batch_max_size', 10)
        self._batch_max_latency_seconds = source_config.get('batch_max_latency_seconds', 60)
        self._file_buffer = []
        self._in_flight = set()
        self._buffer_lock = threading.Lock()
        self._batch_timer = None
        self.info(f"Batching configured with max size: {self._batch_max_size} and max latency: {self._batch_max_latency_seconds}s")

    def add_to_batch(self, raw_event: any):
        """
        Adds a file from an event to the batch buffer, handles renames,
        and checks batch triggers using a unified logic.
        """
        final_path, old_path = self.parse_event(raw_event)
        if not final_path:
            return  # The event was ignored by the parser.

        # Before locking, check if this file is already being processed.
        if final_path in self._in_flight:
            self.debug(f"Ignoring event for in-flight file: {final_path}")
            return

        process_now = False
        with self._buffer_lock:
            # If the event was a move, try to remove the old path from the buffer.
            if old_path and old_path in self._file_buffer:
                self._file_buffer.remove(old_path)

            # Add the new/final path, but only if it's not already present.
            if final_path not in self._file_buffer:
                self._file_buffer.append(final_path)
                self.info(f"Added to buffer: {final_path}. Current size: {len(self._file_buffer)}")

            if not self._file_buffer:
                return

            # Start the timer only if this is the first item in a new batch.
            if len(self._file_buffer) == 1:
                self._batch_timer = threading.Timer(
                    self._batch_max_latency_seconds, self.process_batch
                )
                self._batch_timer.start()

            # If the buffer is full, set a flag to process the batch.
            if len(self._file_buffer) >= self._batch_max_size:
                process_now = True
        
        if process_now:
            self.process_batch()

    def process_batch(self):
        """Processes all files currently in the buffer."""
        files_to_process = []
        with self._buffer_lock:
            if not self._file_buffer:
                return

            if self._batch_timer and self._batch_timer.is_alive():
                self._batch_timer.cancel()
            
            files_to_process = self._file_buffer.copy()
            self._file_buffer.clear()
            # Add the files to the in-flight set to avoid duplicates.
            self._in_flight.update(files_to_process)

        self.info(f"Processing batch of {len(files_to_process)} files...")
        try:
            tasks = {'to do': files_to_process, 'failure': []}
            self.info(f"Batch of {len(files_to_process)} files processed successfully to the next stage.")
            ready = self.transform(tasks)
            completed = self.upload(ready)
            self.save(completed)
            self.clean()
        except Exception as e:
            self.error(f"Failed to process batch: {e}", exc_info=True)
        finally:
            # Always remove the files from the in-flight set after processing.
            self._in_flight.difference_update(files_to_process)

    # -------------------------------------------------------------------------
    # --- State Management Helper Methods (from BaseChecker) ---
    # -------------------------------------------------------------------------

    def load_state(self) -> dict:
        """Load the saved upload state from a previously saved file."""
        with open(os.path.join(self.state_path, self.state_filename)) as f:
            log = json.load(f)
        return log

    def write_state(self, state_data: dict):
        """Write the passed state of successes and failures to file."""
        with open(os.path.join(self.state_path, self.state_filename), 'w') as log:
            json.dump(state_data, log, indent=2)

    def clean_outdated(self, full_state: dict) -> dict:
        """Remove all entries for a particular source file except for the most recent one."""
        def iter_state(key, state_dict):
            for obj in state_dict.get(key, []):
                if 'filename' in obj:
                    yield obj['filename'], obj
                elif 'uploaded' in obj:
                    yield obj['uploaded'], obj

        re_organized = {}
        for category in full_state:
            for filename, event in iter_state(category, full_state):
                if filename not in re_organized:
                    re_organized[filename] = []
                re_organized[filename].append((category, event))

        reduced = copy.deepcopy(EMPTY_LOG)
        for filename, entries in re_organized.items():
            if len(entries) > 1:
                entries = sorted(entries, key=lambda x: x[1]['timestamp'])
            cat, event = entries[-1]
            reduced[cat].append(event)

        return reduced

    def clean_old_success(self, state: dict) -> dict:
        """Delete local files that have been successfully uploaded long enough ago."""
        successes = state.get('success', [])
        kept_success = []
        now = datetime.now().timestamp()
        has_delete = hasattr(self, 'delete_age_hours')
        for uploaded in successes:
            age = (now - uploaded['timestamp']) / (60 * 60)
            if has_delete and self.delete_age_hours >= 0 and age > self.delete_age_hours:
                self.info(f'Deleting {uploaded.get("uploaded")}')
                try:
                    os.remove(uploaded.get("uploaded"))
                except (FileNotFoundError, TypeError):
                    self.warning(f'File was already deleted or path was invalid!')
            else:
                kept_success.append(uploaded)

        new_log = copy.deepcopy(state)
        new_log['success'] = kept_success
        return new_log