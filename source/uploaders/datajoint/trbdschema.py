import importlib
import json
import os
import pathlib
import sys
import traceback
from datetime import datetime

from datajoint import DataJointError
from datajoint.errors import DuplicateError

from source.uploaders.datajoint import DataJointUploader


class TRBDDJUploader(DataJointUploader):

    uploader_name = 'TRBDSPDataJointUploader'
    parsed_filetypes = ['json']
    destination = None
    schema = importlib.import_module("trbd.schema")
    filename2schema = {
        "daily_sleep.json": schema.DailySleepFile,
        "sleep.json": schema.SleepFile,
        "daily_stress.json": schema.DailyStressFile,
        "daily_activity.json": schema.DailyActivityFile,
        "daily_readiness.json": schema.DailyReadinessFile,
        "daily_resilience.json": schema.DailyResilienceFile,
        "daily_spo2.json": schema.DailySpO2File,
        "rest_mode_period.json": schema.RestModePeriodFile,
        "session.json": schema.SessionFile,
        "vO2_max.json": schema.VO2MaxFile,
        "workout.json": schema.WorkoutFile,
        "heartrate.json": schema.HeartRateFile,
    }

    def lookup(self, dj_table, primary_keys, search, squash=True):
        """Search for and return the primary keys for one entry in a table"""
        query = dj_table & search
        matches = query.fetch(*primary_keys)
        if len(matches) == 0:
            raise DataJointError(f'No matching entry in table {dj_table}!')
        elif len(matches) == 1:
            return matches[0]
        elif squash:
            self.warning(f'Found {len(matches)} matching entries. Returning only the first!')
            return matches[0]
        else:
            raise DataJointError(f'Lookup expected exactly one entry, found {len(matches)}!')

    def identify_file_table(self, filename):
        """Determine which DataJoint table corresponds to the file based on its name"""
        try:
            return self.filename2schema[filename]()
        except KeyError:
            raise ValueError(f"Cannot determine file table from filename: {filename}")

    def upload(self, ready):
        successes, errors = [], []
        self.connect_to_database()

        for filepath in ready['to upload']:
            filepath = pathlib.Path(filepath)

            if not filepath.is_file():
                continue

            date = filepath.parent.name

            patient = filepath.parent.parent.name

            filetype = filepath.suffix[1:]
            if filetype not in self.parsed_filetypes:
                continue

            try:
                patient_id = self.lookup(
                    self.schema.Patient(),
                    ['patient_id'],
                    f"patient_id='{patient}'"
                )

                file_table = self.identify_file_table(filepath.name)

                file_stats = os.stat(filepath)

                try:
                    file_table.insert1({
                        'patient_id': patient_id,
                        'date': date,
                        'file_path': str(filepath),
                        'upload_date': datetime.fromtimestamp(file_stats.st_mtime).date(),
                    })
                    self.info(f'Added: {filepath.name} for {patient} on {date}')
                except DuplicateError:
                    self.info(f'Already in DB: {filepath.name} for {patient} on {date}')

                successes.append({
                    'type': 'upload success',
                    'filename': str(filepath),
                    'destination': self.destination,
                })

            except Exception as e:
                error_dict = {
                    'type': 'upload failure',
                    'location': 'CopyUploaderMixin.upload',
                    'filename': str(filepath),
                    'destination': self.destination,
                    'error': str(e),
                    'trace': traceback.format_exception(*sys.exc_info())
                }
                errors.append(error_dict)
                self.warning(f'An upload failed! \n {json.dumps(error_dict, skipkeys=True, indent=2)}')

        return {'success': successes, 'failure': errors}
