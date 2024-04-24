"""
Uploaders that interface with custon DataJoint schemas to insert data into tables

"""
from abc import ABC, abstractmethod
from source.uploaders.base import BaseUploader


class DataJointUploader(BaseUploader, ABC):
    """Parent Uploader for inserting data into custom DataJoint schemas"""

    @property
    @abstractmethod
    def schema(self):
        """Get the schema definition used for this uploader"""
        return NotImplementedError()


class EMUBlackrockDJUploader(DataJointUploader):

    from emu24 import EMU24 as emu_schema

    uploader_name = 'EMUNSPDataJointUploader'
    schema = emu_schema

    def upload(self, ready):

        for filename in ready['to upload']:

            # We know what the path will be of the form ...preamble/emu/patientDatafile/modality/otherbits...
            path_elements = filename.split('/emu/')[-1].split('/')
            patient = path_elements[0]
            admission = path_elements[1]  # Decide where admission info should be stored

            patient_id = patient.split('Datafile')[0]
            admission_id = admission.split('Admission')[-1]

            filetype = filename.split('.')[-1]
            file_table = getattr(self.schema, f'{filetype.capitalize()}Chunks')
            file_table.insert({
                'patient': patient_id,
                'admission': admission_id,
                f'{filetype.lower()}_path': filename,
            })


