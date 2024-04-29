"""
Uploaders that interface with custon DataJoint schemas to insert data into tables

"""
import re
import json
import sys, traceback
from abc import ABC, abstractmethod
from source.uploaders.base import BaseUploader


class DataJointUploader(BaseUploader, ABC):
    """Parent Uploader for inserting data into custom DataJoint schemas"""


class EMUBlackrockDJUploader(DataJointUploader):

    uploader_name = 'EMUNSPDataJointUploader'
    destination = None

    @staticmethod
    def get_or_add(dj_table, pk_name, search, add_data, new_pk=None):
        """Lookup the primary key of an entry in a table, adding a new entry if no matching entries exist"""
        query = dj_table & search
        primary_key = query.fetch1(pk_name)
        if primary_key is None:
            new_pk = len(dj_table) if new_pk is None else new_pk
            dj_table.insert1({pk_name: new_pk, **add_data})
            primary_key = new_pk
        return primary_key

    def connect_to_database(self):
        """Connect to the SQL database using the info in the configuration"""
        import datajoint as dj

        sql_config = self.target_location['sql-config']

        # Replace 'username', 'password', and 'database_name' with your actual database credentials
        dj.config['database.host'] = sql_config['host']
        dj.config['database.user'] = sql_config['username']
        dj.config['database.password'] = sql_config['password']
        dj.config['database.port'] = sql_config['port']

        dj.config['stores'] = self.target_location['stores']

        # Connect to the database
        dj.conn()

        self.destination = f"{sql_config['username']}@{sql_config['host']}:{sql_config['port']}"

    def upload(self, ready):

        successes, errors = [], []
        self.connect_to_database()
        # Define the schema to use by importing the appropriate script
        from emu24 import EMU24 as schema

        for filename in ready['to upload']:

            try:
                # We know what the path will be of the form ...preamble/emu/patientDatafile/modality/otherbits...
                path_elements = filename.split('/emu/')[-1].split('/')

                admission = path_elements[1]  # Decide where admission info should be stored

                # Get the patient ID in the database based on the EMU patient ID
                patient = re.search('([A-Z]{3})Datafile', filename)  # Patient name decoded from the file path
                patient_id = self.get_or_add(
                    schema.Patient(),
                    'patient_id',
                    f'emu_id={patient}',
                    {'emu_id': patient, 'dob': None}
                )

                # TODO: add admission

                # TODO: refactor into TOC Instance
                recording = re.search('Datafile/DATA/([0-9-]*)/', filename)
                recording_id = self.get_or_add(
                    schema.Recording,
                    'recording_id',
                    f'recording_name={recording} and patient={}',
                    {'recording_name': recording},
                )

                schema.TOCInstance.insert1({
                    'patient_id': patient_id,
                    'admission_id': admission_id,
                    'toc_id': toc_id,
                    ''
                })

                # Assume there is only one admission for now
                filetype = filename.split('.')[-1]
                file_table = getattr(schema, f'{filetype.upper()}Chunks')
                file_table.insert1({
                    'patient': patient_id,
                    'admission': admission_id,
                    f'{filetype.lower()}_path': filename,
                })

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
