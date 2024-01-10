from abc import ABC, abstractmethod


class BaseNotifier(ABC):
    """

    """

    def process(self):
        try:
            super().process()
        except Exception as e:
            self.notify(e)

    @abstractmethod
    def notify(self, e):
        """Send a notification of an error occurring to the user/admin"""
