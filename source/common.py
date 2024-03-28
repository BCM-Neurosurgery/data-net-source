import logging
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

    checker_name = "NullChecker"
    transformer_name = "NullTransformer"
    uploader_name = "NullUploader"
    notifier_name = "NullNotifier"

    def __init__(self, source, middle, target):
        """
        Generic creation for all parsers.

        :param source: location to check for new data to be processed
        :param middle: potentially temporary location to store intermediate processed data
        :param target: final location for the parser to leave the ready data
        """
        self.source_location = source
        self.middle_location = middle
        self.target_location = target
        self.loggers = []

    def process(self):
        self.info("STARTING PARSER")
        to_do = self.check()
        if to_do:
            ready = self.transform(to_do)
            complete = self.upload(ready)
        else:
            complete = None
        self.save(complete)
        self.clean()
        self.info("FINISHED\n")

    def describe_parser(self):
        return {
            "git commit": "commitHash",  # TODO: implement commit hashing
            "base": str(type(self)),
            "checker": self.checker_name,
            "transformer": self.transformer_name,  # Defined in the TransformerMixin
            "uploader": self.uploader_name  # Defined in the UploaderMixin
        }

    def check(self):
        """
        Check should look for new data that needs to be uploaded
        See source.checkers.base.BaseChecker for details

        Default is the null checker which does nothing.
        """
        return {'to do': [], 'failure': []}

    def transform(self, tasks):
        """
        Convert the raw data files into a form that is ready for upload
        See source.transformers.base.BaseTransformer for details

        Default is null transformation that does nothing, so just pass back the original files as ready for upload
        """
        return {'to upload': tasks['to do'], 'failure': tasks['failure']}

    def upload(self, ready):
        """
        Upload the ready data files to the data lake with confirmation
        See source.uploaders.base.BaseUploader for details

        Default is NullUploader, which does nothing.
        """
        return {'success': ready['to upload'], 'failure': ready['failure']}

    @abstractmethod
    def save(self, completed):
        """Save the completed files to a log so that they are not re-uploaded"""

    def metadata(self):
        """
        Get the metadata about the data being parsed as a dictionary

        Uploader should override this method to add additional metadata, and include the contents here
        :return:
        """
        meta = {}
        # TODO: Add some basic common metadata
        return meta

    @abstractmethod
    def clean(self):
        """Do cleanup actions"""

    def log(self, message, level=logging.INFO):
        """Generic method to forward logging to all loggers saved for parser"""
        for logger in self.loggers:
            logger.log(level, message)

    def debug(self, message):
        self.log(message, level=logging.DEBUG)

    def info(self, message):
        self.log(message, level=logging.INFO)

    def warning(self, message):
        self.log(message, level=logging.WARN)

    def error(self, message):
        self.log(message, level=logging.ERROR)

    def make_loggers(self, log_config: dict):
        """Prepare the python loggers to manage user notifications and log messages"""
        logging.basicConfig(level=logging.DEBUG, )

        if 'file' in log_config:
            from logging.handlers import RotatingFileHandler
            file_logger = logging.getLogger('file')
            file_logger.setLevel(log_config['file']['level'])
            handler = RotatingFileHandler(
                log_config['file']['filepath'],
                maxBytes=log_config['file']['max_size'],
                backupCount=log_config['file']['max_files']
            )
            handler.setFormatter(
                logging.Formatter(
                    fmt='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
            )
            file_logger.addHandler(handler)
            self.loggers.append(file_logger)

        if 'sentry' in log_config:
            import sentry_sdk as sentry
            from sentry_sdk.integrations.logging import LoggingIntegration

            sentry.init(
                dsn=log_config['sentry']['dsn'],
                integrations=[
                    sentry.integrations.logging.LoggingIntegration(
                        level=log_config['sentry']['level'],  # Capture info and above as breadcrumbs
                        event_level=log_config['sentry']['event_level']  # Send records as events
                    ),
                ],
                release=log_config['sentry']['release']
            )
            self.loggers.append(logging.getLogger('sentry_sdk.errors'))
            self.loggers.append(logging.getLogger('sentry_sdk'))

