"""
Uploaders that interface with custon DataJoint schemas to insert data into tables

"""
import re
import json
import sys, traceback
import pathlib
from abc import ABC, abstractmethod
from datajoint.errors import DataJointError, DuplicateError
from source.uploaders.base import BaseUploader
from datetime import datetime
import os

class DataJointUploader(BaseUploader, ABC):
    """Parent Uploader for inserting data into custom DataJoint schemas"""
    def connect_to_database(self):
        """Connect to the SQL database using the info in the configuration"""
        import datajoint as dj

        sql_config = self.target_location['sql-config']
        dj.config['database.host'] = sql_config['host']
        dj.config['database.user'] = sql_config['username']
        dj.config['database.password'] = sql_config['password']
        dj.config['database.port'] = sql_config['port']
        dj.config['stores'] = self.target_location['stores']

        # Connect to the database
        dj.conn()
        self.destination = f"{sql_config['username']}@{sql_config['host']}:{sql_config['port']}"


class EMUBlackrockDJUploader(DataJointUploader):

    uploader_name = 'EMUNSPDataJointUploader'
    parsed_filetypes = ['nev', 'ns3', 'ns5']
    destination = None

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

    def upload(self, ready):

        successes, errors = [], []
        self.connect_to_database()
        # Define the schema to use by importing the appropriate script
        from emu24 import schema

        for filename in ready['to upload']:

            # TODO: move these to checkers after we merge with oura-updates and config file improvements
            # Skip files that are not in a DATA directory
            if 'DATA' not in filename:
                continue
            filename = pathlib.Path(filename).as_posix()
            filetype = filename.split('.')[-1]
            if filetype not in self.parsed_filetypes:
                # Skip file types that are not listed as parsable
                continue

            try:
                # Get the patient ID in the database based on the EMU patient ID
                patient = re.search(r'([A-Z]*)Datafile', filename).group(1)  # Patient name decoded from the file path
                patient_id = self.lookup(
                    schema.Patient(),
                    ['patient_id'],
                    f"emu_id='{patient}'"
                )

                # Assume that we want the id of most recent admission
                query = schema.Admission() & f"patient_id='{patient_id}'"
                admissions = query.fetch()
                sort_ready = [(date, id) for (_, id, date) in admissions]
                by_date = [id for (date, id) in sorted(sort_ready, key=lambda pair: pair[0])]
                admission_id = by_date[-1]

                # Get the ID of this toc instance, or make a new one if necessary
                toc_name = re.search(r'Datafile/DATA/([0-9-]*)/', filename).group(1)
                try:
                    toc_id = self.lookup(
                        schema.TOCInstance(),
                        ['toc_id'],
                        f"patient_id='{patient_id}' AND admission_id='{admission_id}' AND base_file='{toc_name}'",
                        squash=True
                    )
                except DataJointError as e:
                    self.warning(f'Got an error while looking up the TOC instance: {e}')
                    self.warning('Making a new TOC mode instance')
                    new_toc_id = len(schema.TOCInstance())
                    schema.TOCInstance().insert1({
                        'patient_id': patient_id,
                        'admission_id': admission_id,
                        'toc_id': new_toc_id,
                        'base_file': toc_name
                    })
                    toc_id = new_toc_id

                # Get the NSP and Chunk IDs from the filename
                chunk_data = re.search(r'NSP([12])-[0-9-]*-([0-9]{3})\.[nsev0-9]{3}', filename)
                nsp_id = chunk_data.group(1)
                chunk_id = chunk_data.group(2)

                # Insert into the appropriate table based on the file type
                file_table = getattr(schema, f'{filetype.upper()}Chunks')
                try:
                    file_table.insert1({
                        'patient_id': patient_id,
                        'admission_id': admission_id,
                        'toc_id': toc_id,
                        'nsp_id': nsp_id,
                        'chunk_id': chunk_id,
                        f'{filetype.lower()}_file': filename,
                    })
                    self.info(f'Added: {filetype} for {patient} at {toc_name} NSP{nsp_id} chunk {chunk_id}')
                except DuplicateError:
                    self.info(f'Already in DB: {filetype} for {patient} at {toc_name} NSP{nsp_id} chunk {chunk_id}')

            except Exception as e:
                error_dict = {
                    'type': 'upload failure',
                    'location': 'CopyUploaderMixin.upload',
                    'filename': filename,
                    'destination': self.destination,
                    'error': str(e),
                    'trace': traceback.format_exception(*sys.exc_info())
                }
                errors.append(error_dict)
                self.warning(f'An upload failed! \n {json.dumps(error_dict, skipkeys=True, indent=2)}')
            else:
                successes.append({
                    'type': 'upload success',
                    'filename': filename,
                    'destination': self.destination,
                })
        return {
            'success': successes, 'failure': errors
        }


class TRBDDJUploader(DataJointUploader):

    from trbd import schema
    uploader_name = 'TRBDSPDataJointUploader'
    parsed_filetypes = ['json']
    destination = None
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
        from trbd import schema

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
                    schema.Patient(),
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
