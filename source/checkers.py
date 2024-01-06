import json
import os


def load_success_log(log_location):
    with open(log_location) as f:
        log = json.load(f)
    uploaded = log['success']
    return uploaded


class WholeDirCheckerMixin:
    """
    Mixin to a parser that checks whether an entire directory has already been uploaded or not
    """

    def check(self, source_dir):
        dirs_here = [
            directory for directory in os.listdir(source_dir)
            if os.path.isdir(os.path.join(source_dir, directory))
        ]

        # TODO: the log will need to be parsed somehow, not sure what other info we will save here
        already_uploaded = load_success_log(os.path.join(source_dir, 'upload_log.json'))

        to_upload = [
            directory for directory in dirs_here
            if directory not in already_uploaded
        ]
        return to_upload

    def save(self):
        # TODO: Implement a save
        pass

