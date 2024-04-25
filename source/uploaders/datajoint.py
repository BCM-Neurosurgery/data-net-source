"""
Uploaders that interface with custon DataJoint schemas to insert data into tables

"""
import json
import sys, traceback
from abc import ABC, abstractmethod
from source.uploaders.base import BaseUploader


class DataJointUploader(BaseUploader, ABC):
    """Parent Uploader for inserting data into custom DataJoint schemas"""


class EMUBlackrockDJUploader(DataJointUploader):

    uploader_name = 'EMUNSPDataJointUploader'
    destination = None

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
                patient = path_elements[0]
                admission = path_elements[1]  # Decide where admission info should be stored

                patient_id = patient.split('Datafile')[0]
                admission_id = admission.split('Admission')[-1]

                filetype = filename.split('.')[-1]
                file_table = getattr(schema, f'{filetype.capitalize()}Chunks')
                file_table.insert({
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

