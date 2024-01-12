import runeq

from source.checkers.base import BaseChecker


class RuneAPICheckerMixin(BaseChecker):

    checker_name = "RuneAPIChecker"

    def check(self):
        """
        Search for new data from the RUNE API
        NOTE: the source location for this is ignored
        """
        runeq.initialize()

        # First get all available patients and devices
        all_patients = runeq.resources.patient.get_all_patients()

    def save(self, completed):
        """Log which new time periods of RUNE data have been uploaded"""
        pass
