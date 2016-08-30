from dart.util.logging_utils import DartLogger
from dart.message.trigger_listener import TriggerListener
from dart.tool.tool_runner import Tool
from dart.worker.worker import Worker

_logger = DartLogger(__name__)

class TriggerWorker(Tool):
    def __init__(self):
        super(TriggerWorker, self).__init__(_logger)
        self._listener = self.app_context.get(TriggerListener)

    def run(self):
        assert isinstance(self._listener, TriggerListener)
        self._listener.await_call()

if __name__ == '__main__':
    Worker(TriggerWorker(), _logger).run()
