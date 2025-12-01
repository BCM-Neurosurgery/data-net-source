from source.common import ParserCommon
from source.checkers.local import DBFileCheckerMixin
from source.uploaders.simple import CopyUploaderMixin
import os
import requests
from datetime import datetime, timedelta, time, date


class SurveyChecker(DBFileCheckerMixin): 
    def dump_data(self, payload=None):
        # for survey data, get from midnight of current day to 24 hrs prior
        current_date = date.today()
        midnight_local = datetime.combine(current_date, time.min)
        # now get 24 hrs prior
        midnight_prior = midnight - timedelta(days=1)
        payload = {
            "query_start": midnight_prior.isoformat(),
            "query_end": midnight_local.isoformat()
        }
        return res = requests.post(f"{db_url}/{dump_route}", data=payload)


class SurveyParser(SurveyChecker, CopyUploaderMixin, ParserCommon):
    """Parser for copying new survey data to the correct location on elias"""





