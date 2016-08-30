from dart.util.logging_utils import DartLogger
import logging.config

from dart.message.subscription_listener import SubscriptionListener
from dart.tool.tool_runner import Tool
from dart.worker.worker import Worker

_logger = DartLogger(__name__)


class SubscriptionWorker(Tool):
    def __init__(self):
        super(SubscriptionWorker, self).__init__(_logger)
        self._listener = self.app_context.get(SubscriptionListener)

    def run(self):
        assert isinstance(self._listener, SubscriptionListener)
        self._listener.await_call()


if __name__ == '__main__':
    Worker(SubscriptionWorker(), _logger).run()
