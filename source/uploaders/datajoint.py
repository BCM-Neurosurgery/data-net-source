"""
Uploaders that interface with custon DataJoint schemas to insert data into tables

"""
import re
import json
import sys, traceback
from abc import ABC, abstractmethod
from datajoint.errors import DataJointError
from source.uploaders.base import BaseUploader


class DataJointUploader(BaseUploader, ABC):
    """Parent Uploader for inserting data into custom DataJoint schemas"""


class EMUBlackrockDJUploader(DataJointUploader):

    uploader_name = 'EMUNSPDataJointUploader'
    parsed_filetypes = ['nev', 'ns3', 'ns3']
    destination = None

    @staticmethod
    def lookup(dj_table, primary_keys, search):
        """Search for and return the primary keys for one entry in a table"""
        query = dj_table & search
        pks = query.fetch1(*primary_keys)
        return pks

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

            filetype = filename.split('.')[-1]
            if filetype not in self.parsed_filetypes:
                # Skip file types that are not listed as parsable
                continue

            try:
                # Get the patient ID in the database based on the EMU patient ID
                patient = re.search(r'([A-Z]{3})Datafile', filename).group(1)  # Patient name decoded from the file path
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
                        f"patient_id='{patient_id}' AND admission_id='{admission_id}' AND base_file='{toc_name}'"
                    )
                except DataJointError:
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
                file_table.insert1({
                    'patient_id': patient_id,
                    'admission_id': admission_id,
                    'toc_id': toc_id,
                    'nsp_id': nsp_id,
                    'chunk_id': chunk_id,
                    f'{filetype.lower()}_file': filename,
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
