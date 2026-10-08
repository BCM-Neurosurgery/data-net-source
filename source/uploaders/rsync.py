"""Batched rsync uploads. Requires OpenSSH and rsync >= 3.2.3 on both hosts."""

import fcntl
import hashlib
import os
import re
import shlex
import socket
import stat
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from source.uploaders.base import BaseUploader, FileSystemPathsMixin


class RsyncUploaderMixin(FileSystemPathsMixin, BaseUploader):
    """Use target['ssh-config'] with hostname, username, port, key_filename, timeout.

    Authentication uses OpenSSH keys/agent/config and known_hosts, never passwords.
    Only queued files are sent. A temporary symlink tree applies rebuild_filepath
    without copying file contents. Partial files live beside their destination in
    a stable, parser-specific directory and are reused and removed by rsync.
    """

    uploader_name = 'RsyncUploader'
    rsync_binary = 'rsync'
    rsync_io_timeout = 120  # Idle I/O timeout, not a total duration limit.

    def _rsync_command(self, stage):
        config = self.target_location['ssh-config']
        supported = {'hostname', 'username', 'port', 'key_filename', 'timeout'}
        unsupported = set(config) - supported
        if unsupported:
            raise ValueError(f'Unsupported rsync ssh-config keys: {sorted(unsupported)}')
        host = config['hostname']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', host) or host.startswith('-'):
            raise ValueError('SSH hostname must be a hostname, IPv4 address, or SSH config alias')
        connect_timeout = int(config.get('timeout', 30))
        io_timeout = int(self.rsync_io_timeout)
        if connect_timeout <= 0 or io_timeout <= 0:
            raise ValueError('SSH connection and rsync idle timeouts must be positive')
        ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
               '-o', f'ConnectTimeout={connect_timeout}',
               '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3']
        if 'username' in config:
            ssh += ['-l', config['username']]
        if 'port' in config:
            ssh += ['-p', str(config['port'])]
        keys = config.get('key_filename', [])
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            ssh += ['-i', os.path.expanduser(key)]
        target = self.target_location['path']
        if not target or '\0' in target:
            raise ValueError('A nonempty destination path is required')
        owner = f'{socket.gethostname()}:{Path(self.state_path).resolve()}'
        namespace = hashlib.sha256(owner.encode()).hexdigest()[:16]
        # New directories follow the receiver's umask/default ACL, rather than
        # inheriting the private temporary staging root's mode (0700).
        return [self.rsync_binary, '--times', '--omit-dir-times', '--copy-links',
                '--chmod=Dugo=rwx',
                '--mkpath', '--protect-args', '--from0', '--files-from=-',
                '--out-format=%i\t%n', f'--timeout={io_timeout}',
                f'--partial-dir=.rsync-partial-{namespace}',
                '-e', shlex.join(ssh), '--', f'{stage}/', f'{host}:{target.rstrip("/")}/']

    @staticmethod
    def _updates(output):
        """Decode rsync's octal filename escaping, including newlines and backslashes."""
        updates = {}
        for line in output.splitlines():
            item, separator, name = line.partition(b'\t')
            if separator and len(item) == 11 and item[1:2] == b'f':
                name = re.sub(rb'\\#([0-7]{3})',
                              lambda match: bytes([int(match[1], 8)]), name)
                updates[os.fsdecode(name)] = item
        return updates

    @staticmethod
    def _run(command, manifest):
        result = subprocess.run(command, input=manifest, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env={**os.environ, 'LC_ALL': 'C'})
        if result.returncode:
            detail = os.fsdecode(result.stderr).strip()
            raise RuntimeError(f'rsync exited {result.returncode}: {detail}')
        return RsyncUploaderMixin._updates(result.stdout)

    @staticmethod
    def _source_version(filename):
        info = os.stat(filename)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Only regular files can be uploaded')
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns

    def upload(self, ready):
        results = {'success': [], 'failure': list(ready['failure']), 'skipped': []}
        if not ready['to upload']:
            return results

        def record(category, filename, destination, error=None):
            event = {'type': {'success': 'upload success', 'failure': 'upload failure',
                              'skipped': 'RemoteFileExists'}[category],
                     'filename': filename, 'destination': destination,
                     'timestamp': datetime.now().timestamp()}
            if error is not None:
                event['error'] = str(error)
                self.warning(f'Upload failed for {filename}: {error}')
            results[category].append(event)

        # Reject ambiguous mappings before sending either file to that destination.
        entries = {}
        for filename in dict.fromkeys(ready['to upload']):
            destination = 'Failed to determine!'
            try:
                relative = Path(self.ready_relative_filepath(filename))
                if relative.is_absolute() or '..' in relative.parts or not relative.name:
                    raise ValueError(f'Destination must be a relative file path: {relative}')
                destination = str(Path(self.target_location['path']) / relative)
                version = self._source_version(filename)
                entries.setdefault(relative.as_posix(), []).append((filename, destination, version))
            except Exception as error:
                record('failure', filename, destination, error)
        files = {}
        for relative, group in entries.items():
            if len(group) != 1:
                for filename, destination, _ in group:
                    record('failure', filename, destination, 'Multiple sources map to the same destination')
            else:
                files[relative] = group[0]
        if not files:
            return results

        try:
            # The same parser must not have concurrent writers to its partial files.
            with open(Path(self.state_path) / 'rsync-upload.lock', 'a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with tempfile.TemporaryDirectory(prefix='rsync-upload-', dir=self.state_path) as stage:
                    for relative, (filename, _, _) in files.items():
                        link = Path(stage) / relative
                        link.parent.mkdir(parents=True, exist_ok=True)
                        link.symlink_to(Path(filename).absolute())
                    manifest = b''.join(os.fsencode(name) + b'\0' for name in sorted(files))
                    command = self._rsync_command(stage)
                    overwrite = self.target_location.get('allow-overwrite', False)
                    options = [] if overwrite else ['--ignore-existing']
                    self.info(f'Uploading {len(files)} queued files with rsync')
                    copied = self._run(command[:1] + options + command[1:], manifest)
                    # A metadata-only comparison catches legacy truncated final files
                    # skipped by --ignore-existing. No checksum pass or recursive scan.
                    verify = ['--dry-run', '--size-only']
                    pending = self._run(command[:1] + verify + command[1:], manifest)
        except Exception as error:
            # A failed batch never advances parser state, even for earlier files.
            # Completed files are checked by rsync and skipped on the next retry.
            for filename, destination, _ in files.values():
                record('failure', filename, destination, error)
            return results

        for relative, (filename, destination, version) in files.items():
            try:
                if self._source_version(filename) != version:
                    raise RuntimeError('Source changed during upload; leaving it queued for retry')
                if pending.get(relative, b'')[:1] == b'<':
                    raise RuntimeError('Destination is missing or has a different size; '
                                       'enable allow-overwrite to repair an existing partial file')
            except Exception as error:
                record('failure', filename, destination, error)
            else:
                # With overwrite enabled, a verified unchanged file is also complete
                # (including files finished before a previous batch failure). This
                # keeps the checker's success-based source retention working.
                category = 'success' if overwrite or copied.get(relative, b'')[:1] == b'<' else 'skipped'
                record(category, filename, destination)
        return results
