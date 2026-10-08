import errno
import io
import os
import shlex
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from source.checkers.local import FileCheckerMixin
from source.common import ParserCommon
from source.uploaders.base import FileSystemUploader
from source.uploaders.ssh import SCPUploaderMixin


class SCPParser(FileCheckerMixin, SCPUploaderMixin, ParserCommon):
    pass


class LocalSFTP:
    """Filesystem-backed SFTP double with no-clobber and POSIX rename semantics."""

    def stat(self, filename):
        attributes = os.stat(filename)
        return SimpleNamespace(st_mode=attributes.st_mode, st_size=attributes.st_size)

    def rename(self, source, destination):
        # Publish without replacing a final file created by another uploader.
        os.link(source, destination)
        os.unlink(source)

    def posix_rename(self, source, destination):
        os.replace(source, destination)

    def remove(self, filename):
        os.remove(filename)


class SCPUploadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.source = root / 'source'
        self.target = root / "target ' $data"
        self.state = root / 'state'
        self.source.mkdir()
        self.state.mkdir()
        self.filename = self.source / "video ' $recording.mp4"
        self.filename.write_bytes(b'complete video data')
        self.parser = SCPParser(
            str(self.state), source={'path': str(self.source), 'check_for_modifications': False},
            target={'path': str(self.target)}
        )
        self.parser.save_state(success=[], failure=[], skipped=[])
        self.parser.sftp = LocalSFTP()
        self.parser.scp = Mock()
        self.parser.scp.put.side_effect = shutil.copyfile
        self.parser.make_connection = Mock()
        self.parser.close_connection = Mock()
        self.parser._run_remote_command = Mock(side_effect=self.make_directory)
        self.destination = self.parser.destination_filepath(str(self.filename))

    def make_directory(self, command):
        arguments = shlex.split(command)
        self.assertEqual(arguments[:3], ['mkdir', '-p', '--'])
        Path(arguments[3]).mkdir(parents=True, exist_ok=True)
        return ''

    def upload(self):
        return self.parser.upload({'to upload': [str(self.filename)], 'failure': []})

    def assert_result(self, result, category):
        self.assertEqual({name: len(events) for name, events in result.items()},
                         {name: int(name == category) for name in ('success', 'failure', 'skipped')})

    def assert_no_temporary_upload(self):
        self.assertEqual(list(self.target.glob('.upload-*.part')), [])

    def test_success_is_published_only_after_transfer(self):
        def copy(source, temporary):
            self.assertFalse(self.destination.exists())
            self.assertNotEqual(Path(temporary), self.destination)
            self.assertEqual(Path(temporary).parent, self.destination.parent)
            shutil.copyfile(source, temporary)
            self.assertFalse(self.destination.exists())

        self.parser.scp.put.side_effect = copy
        self.assert_result(self.upload(), 'success')
        self.assertEqual(self.destination.read_bytes(), self.filename.read_bytes())
        self.assert_no_temporary_upload()
        self.parser.close_connection.assert_called_once()

    def test_timeout_cleans_partial_and_next_run_retries(self):
        def interrupted(source, temporary):
            Path(temporary).write_bytes(b'complete')
            raise TimeoutError('transfer interrupted')

        self.parser.scp.put.side_effect = interrupted
        result = self.upload()
        self.assert_result(result, 'failure')
        self.assertFalse(self.destination.exists())
        self.assert_no_temporary_upload()
        self.parser.save(result)
        self.parser.clean()
        self.assertEqual(self.parser.check()['to do'], [str(self.filename)])
        self.parser.scp.put.side_effect = shutil.copyfile
        result = self.upload()
        self.assert_result(result, 'success')
        self.parser.save(result)
        self.parser.clean()
        self.assertEqual(len(self.parser.load_state()['failure']), 0)
        self.assertEqual(self.parser.check()['to do'], [])

    def test_existing_partial_stays_failure_after_save_and_cleanup(self):
        self.target.mkdir()
        self.destination.write_bytes(b'partial')
        for _ in range(2):
            result = self.upload()
            self.assert_result(result, 'failure')
            self.assertIn('source=19 bytes, destination=7 bytes', result['failure'][0]['error'])
            self.parser.save(result)
            self.parser.clean()
            self.assertEqual(len(self.parser.load_state()['failure']), 1)
            self.assertEqual(self.parser.load_state()['skipped'], [])
            self.assertEqual(self.parser.check()['to do'], [str(self.filename)])
        self.assertEqual(self.destination.read_bytes(), b'partial')
        self.parser.scp.put.assert_not_called()

    def test_complete_existing_file_can_clear_previous_failure(self):
        self.parser.save({'success': [], 'skipped': [], 'failure': [{
            'filename': str(self.filename), 'type': 'upload failure'
        }]})
        self.target.mkdir()
        shutil.copyfile(self.filename, self.destination)
        result = self.upload()
        self.assert_result(result, 'skipped')
        self.parser.save(result)
        self.parser.clean()
        self.assertEqual(self.parser.load_state()['failure'], [])
        self.assertEqual(self.parser.check()['to do'], [])
        self.parser.scp.put.assert_not_called()

    def test_zero_byte_file_is_validated_and_skipped(self):
        self.filename.write_bytes(b'')
        self.assert_result(self.upload(), 'success')
        self.assert_result(self.upload(), 'skipped')

    def test_silent_short_transfer_is_failure(self):
        self.parser.scp.put.side_effect = lambda source, temporary: Path(temporary).write_bytes(b'short')
        result = self.upload()
        self.assert_result(result, 'failure')
        self.assertIn('Uploaded size mismatch', result['failure'][0]['error'])
        self.assertFalse(self.destination.exists())
        self.assert_no_temporary_upload()

    def test_source_modified_during_transfer_is_failure(self):
        def changed(source, temporary):
            shutil.copyfile(source, temporary)
            original = os.stat(source)
            os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns + 1000000000))

        self.parser.scp.put.side_effect = changed
        result = self.upload()
        self.assert_result(result, 'failure')
        self.assertIn('Source changed', result['failure'][0]['error'])
        self.assertFalse(self.destination.exists())
        self.assert_no_temporary_upload()

    def test_permission_error_is_failure_not_missing(self):
        self.parser.sftp.stat = Mock(side_effect=PermissionError(errno.EACCES, 'denied'))
        self.assert_result(self.upload(), 'failure')
        self.parser.scp.put.assert_not_called()

    def test_directory_destination_is_failure(self):
        self.destination.mkdir(parents=True)
        self.assert_result(self.upload(), 'failure')
        self.parser.scp.put.assert_not_called()

    def test_mkdir_failure_stops_transfer(self):
        self.parser._run_remote_command.side_effect = ChildProcessError('mkdir failed')
        self.assert_result(self.upload(), 'failure')
        self.parser.scp.put.assert_not_called()

    def test_failed_rename_cleans_temporary(self):
        self.parser.sftp.rename = Mock(side_effect=OSError('rename failed'))
        self.assert_result(self.upload(), 'failure')
        self.assertFalse(self.destination.exists())
        self.assert_no_temporary_upload()

    def test_cleanup_failure_preserves_original_error_and_next_run_ignores_temporary(self):
        def interrupted(source, temporary):
            Path(temporary).write_bytes(b'partial')
            raise TimeoutError('original timeout')

        self.parser.scp.put.side_effect = interrupted
        self.parser.sftp.remove = Mock(side_effect=OSError('disconnected'))
        result = self.upload()
        self.assert_result(result, 'failure')
        self.assertEqual(result['failure'][0]['error'], 'original timeout')
        self.assertFalse(self.destination.exists())
        stale_temporary = list(self.target.glob('.upload-*.part'))
        self.assertEqual(len(stale_temporary), 1)
        self.parser.scp.put.side_effect = shutil.copyfile
        self.assert_result(self.upload(), 'success')
        self.assertTrue(stale_temporary[0].exists())

    def test_concurrent_final_file_is_not_overwritten(self):
        def raced(source, temporary):
            shutil.copyfile(source, temporary)
            self.destination.write_bytes(b'other uploader')

        self.parser.scp.put.side_effect = raced
        self.assert_result(self.upload(), 'failure')
        self.assertEqual(self.destination.read_bytes(), b'other uploader')
        self.assert_no_temporary_upload()

    def test_overwrite_publishes_validated_replacement(self):
        self.target.mkdir()
        self.destination.write_bytes(b'old partial')
        self.parser.target_location['allow-overwrite'] = True

        def copy(source, temporary):
            self.assertEqual(self.destination.read_bytes(), b'old partial')
            shutil.copyfile(source, temporary)

        self.parser.scp.put.side_effect = copy
        self.assert_result(self.upload(), 'success')
        self.assertEqual(self.destination.read_bytes(), self.filename.read_bytes())
        self.assert_no_temporary_upload()

    def test_failed_overwrite_preserves_old_final(self):
        self.target.mkdir()
        self.destination.write_bytes(b'old partial')
        self.parser.target_location['allow-overwrite'] = True
        self.parser.scp.put.side_effect = lambda source, temporary: Path(temporary).write_bytes(b'short')
        self.assert_result(self.upload(), 'failure')
        self.assertEqual(self.destination.read_bytes(), b'old partial')
        self.assert_no_temporary_upload()

    def test_remote_command_exit_status_is_checked(self):
        stdout = io.BytesIO(b'')
        stdout.channel = Mock()
        stdout.channel.recv_exit_status.return_value = 1
        self.parser.ssh = Mock()
        self.parser.ssh.exec_command.return_value = (None, stdout, io.BytesIO(b'permission denied'))
        with self.assertRaisesRegex(ChildProcessError, 'permission denied'):
            SCPUploaderMixin._run_remote_command(self.parser, 'mkdir -p -- /target')

    def test_unavailable_sftp_closes_ssh_connection(self):
        self.parser.target_location['ssh-config'] = {}
        with patch('source.uploaders.ssh.SSHClient') as client:
            client.return_value.open_sftp.side_effect = OSError('SFTP unavailable')
            with self.assertRaisesRegex(OSError, 'SFTP unavailable'):
                SCPUploaderMixin.make_connection(self.parser)
            client.return_value.close.assert_called_once()

    def test_close_failure_still_closes_remaining_connections(self):
        self.parser.scp.close.side_effect = OSError('SCP close failed')
        self.parser.sftp = Mock()
        self.parser.ssh = Mock()
        with self.assertRaisesRegex(OSError, 'SCP close failed'):
            SCPUploaderMixin.close_connection(self.parser)
        self.parser.sftp.close.assert_called_once()
        self.parser.ssh.close.assert_called_once()

    def test_other_filesystem_uploaders_keep_existence_behavior(self):
        uploader = Mock()
        uploader.check_exists.return_value = True
        self.assertTrue(FileSystemUploader.check_complete(uploader, self.filename, self.destination))
        uploader.check_exists.assert_called_once_with(self.destination)


if __name__ == '__main__':
    unittest.main()
