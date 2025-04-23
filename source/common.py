import os
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

    def __init__(self, state_path, source=None, middle=None, target=None):
        """
        Generic creation for all parsers.

        :param state_path: Path to the directory where the parser should keep track of the upload state
        :param source: location to check for new data to be processed
        :param middle: (optional) location to store intermediate processed data
        :param target: final location for the parser to leave the ready data
        """
        self.state_path = state_path
        self.loggers = []

        #: List of functions that send a startup notification
        self.start_notifiers = []

        #: List of functions that send an end notification. Should accept a unix-style exit code
        self.end_notifiers = []

        if source is None:
            raise ValueError("Source configuration must be set!")
        else:
            self.source_location = source

        if middle is None:
            # This means there is no transformer, so we just copy over the data from source to pass to uploader
            self.middle_location = source
        else:
            self.middle_location = middle

        if target is None:
            raise ValueError("Target configuration must be set!")
        else:
            self.target_location = target

    def process(self):
        self.start_notify()
        try:
            to_do = self.check()
            self.info(f'Found {len(to_do["to do"])} new tasks...')
            if to_do:
                ready = self.transform(to_do)
                complete = self.upload(ready)
            else:
                complete = None
            self.info(f'Saving {len(complete["success"])} successes and {len(complete["failure"])} failures')
            self.save(complete)
            self.info('Performing cleanup')
            self.clean()
        # Always send an end notification
        except Exception as e:
            self.end_notify(1) #TODO: upgrade to send more meaningful exit codes
            raise e
        else:
            self.end_notify(0)

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

    def describe_parser(self):
        return {
            "git commit": "commitHash",  # TODO: implement commit hashing
            "base": str(type(self)),
            "checker": self.checker_name,
            "transformer": self.transformer_name,  # Defined in the TransformerMixin
            "uploader": self.uploader_name  # Defined in the UploaderMixin
        }

    def start_notify(self):
        """Call each of the start notification functions created as part of logging setup"""
        self.info("STARTING PARSER")
        for func in self.start_notifiers:
            func()

    def end_notify(self, status_code):
        """
        Call each of the end notification functions created as part of logging setup

        Note that errors as a result of upload failures are not considered a parser failure, as the parser completed
        its primary task (running) successfully even if there are upload failures. These individual uplaod failures
        should be sent independently as individual error log messages.
        """
        for func in self.end_notifiers:
            func(status_code)
        self.info(f"FINISHED with status code ({status_code})\n")

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

        # Dump detailed log to a log file on the system
        if 'file' in log_config:
            from logging.handlers import RotatingFileHandler
            file_logger = logging.getLogger('file')
            file_logger.setLevel(log_config['file']['level'])

            if 'filepath' in log_config['file']:
                filepath = log_config['file']['filepath']
            elif 'filename' in log_config['file']:
                filepath = os.path.join(self.state_path, log_config['file']['filename'])
            else:
                filepath = os.path.join(self.state_path, 'upload_log.txt')

            handler = RotatingFileHandler(
                filepath,
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

        # Check in regularly with a healthchecks.io server which should (separately) be listening for this task
        if 'healthchecks' in log_config:
            import requests
            hc_config = log_config['healthchecks']
            server_url = hc_config['url']

            # Build the full url to where to send
            # Prefer uuid over ping-key + slug
            if 'uuid' in hc_config:
                uuid = hc_config['uuid']
                full_hc_url = f'{server_url}/{uuid}'
            elif 'ping-key' in hc_config:
                ping_key = hc_config['ping_key']
                # If specified, use the custom slug, otherwise use the simplified parser name as a slug
                slug = hc_config['slug'] if 'slug' in hc_config else self.__class__.__name__.lower()
                full_hc_url = f'{server_url}/{ping_key}/{slug}'
            else:
                raise KeyError("Must specify either 'uuid' or a 'ping_key' for healthchecks logging to work!")

            # Create a handler that sends logs to Healthchecks.io
            class HealthchecksHandler(logging.Handler):
                def emit(self, record):
                    headers = {'Content-Type': 'text/plain; charset=utf-8'}
                    log_entry = self.format(record).encode('utf-8')
                    endpoint = f"{full_hc_url}/log"
                    try:
                        requests.post(endpoint, data=log_entry, headers=headers)
                    except requests.exceptions.RequestException as e:
                        print(f"Error sending log to Healthchecks: {e}")

            hc_logger = logging.getLogger('healthchecks')
            hc_logger.setLevel(log_config['healthchecks']['level'])
            hc_handler = HealthchecksHandler()
            hc_handler.setFormatter(
                logging.Formatter(
                    fmt='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
            )
            hc_logger.addHandler(hc_handler)
            self.loggers.append(hc_logger)

            # Append a start function that sends a genetic start ping on parser startup
            def hc_start_notify():
                requests.post(f'{full_hc_url}/start')
            self.start_notifiers.append(hc_start_notify)

            # Append a end function that sends a ping with the exit code (0/1 = success/failure)
            def hc_end_notify(status_code: int):
                requests.post(f'{full_hc_url}/{status_code}')
            self.end_notifiers.append(hc_end_notify)

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

