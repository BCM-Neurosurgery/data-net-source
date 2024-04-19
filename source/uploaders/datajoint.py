"""
Uploaders that interface with custon DataJoint schemas to insert data into tables

"""
from abc import ABC, abstractmethod
from source.uploaders.base import BaseUploader


class DataJointUploader(BaseUploader, ABC):
    """Parent Uploader for inserting data into custom DataJoint schemas"""


class EMUBlackrockDJUploader(DataJointUploader):

    uploader_name = 'EMUNSPDataJointUploader'

    def upload(self, ready):
        pass

    schema = None


