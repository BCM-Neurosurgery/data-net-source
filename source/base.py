from abc import ABC, abstractmethod


class ParserCommon(ABC):

    """
    Each parser must consist of 3 parts:
        - A Checker: check for new data to be processed, and saves completion once data is uploaded
        - A Transformer: apply any necessary transformations to the data
        - A Uploader: send the ready data up to the data lake

    Each parser may also include any of the following:
        - A logger: which
    """
    def __init__(self):
        self.folder_path = '/home/weill2/Documents/data-net-subject/source_data/temp'

    def process(self):
        to_do = self.check()
        ready = self.transform(to_do)
        complete = self.upload(ready)
        self.save(complete)

    @abstractmethod
    def check(self):
        """Check should look for new data that needs to be uploaded"""
        return []  # Return a list of files that need to be processed

    @abstractmethod
    def transform(self, to_do):
        """Convert the raw data files into a form that is ready for upload"""
        return []  # Return a list of files that are ready for upload

    @abstractmethod
    def upload(self, ready):
        """Upload the ready data files to the data lake with confirmation"""
        return []  # Return a list of files that were successfully uploaded

    @abstractmethod
    def save(self, completed):
        """Save the completed files to a log so that they are not re-uploaded"""
