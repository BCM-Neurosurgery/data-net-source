import os
import json

from abc import abstractmethod, ABC

from source.checkers.base import BaseChecker


class BaseAPIChecker(BaseChecker, ABC):
    """
    Base checker that additionally implements a method to get patient  API keys

    Config file 'source_location' for all checkers of this type must include a 'patients' key, described in the
    .patients() function
    """
    source_location = {
        'patients': "path/to/patient/keys/json/"
    }

    @property
    def patients(self) -> dict:

        patient_info = self.source_location['patients']

        if isinstance(patient_info, dict):
            # The config file has the API keys for the patients directly
            patient_keys = patient_info

        elif isinstance(patient_info, str):
            # Assume that this is the path to a file which contains a list of API keys
            # This is implemented to allow separation of the parser configuration and the list of patients to actively
            # query the API for. Very important if the patient information needs to be updated more often or by other
            # agents than those that should update the parser configuration
            with open(patient_info) as json_file:
                patient_keys = json.load(json_file)

        else:
            raise ValueError('The patient entry in source_location is not in a valid format')

        return patient_keys
