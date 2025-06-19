from abc import ABC

from source.uploaders.base import BaseUploader


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
