"""
Uploaders that interface with custon DataJoint schemas to insert data into tables

"""
from abc import ABC, abstractmethod
from source.uploaders.base import BaseUploader


class DataJointUploader(BaseUploader, ABC):
    """Parent Uploader for inserting data into custom DataJoint schemas"""


class EMUBlackrockDJUploader(DataJointUploader):

    import datajoint as dj
    uploader_name = 'EMUNSPDataJointUploader'

    def connect_to_database(self):
        """Connect to the SQL database using the info in the configuration"""
        sql_config = self.target_location['sql-config']

        print('\n')
        print('PRE CONFIG:')
        print('Datajoint')
        print(self.dj)
        print('\n\n')
        print('DJ Config')
        print(self.dj.config)
        print('\n')

        # Replace 'username', 'password', and 'database_name' with your actual database credentials
        self.dj.config['database.host'] = sql_config['host']
        self.dj.config['database.user'] = sql_config['username']
        self.dj.config['database.password'] = sql_config['password']
        self.dj.config['database.port'] = sql_config['port']

        self.dj.config['stores'] = self.target_location['stores']

        print('\n')
        print('POST CONFIG:')
        print('Datajoint')
        print(self.dj)
        print('\n\n')
        print('DJ Config')
        print(self.dj.config)
        print('\n')

        # Connect to the database
        self.dj.conn()

    def upload(self, ready):

        # Define the schema to use by importing the appropriate script
        from emu24 import EMU24 as schema

        for filename in ready['to upload']:

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


