from dart.util.logging_utils import DartLogger
import os
import time
import traceback

from dart.client.python.dart_client import Dart
from dart.engine.no_op.metadata import NoOpActionTypes
from dart.model.engine import ActionResult, ActionResultState
from dart.tool.tool_runner import Tool

_logger = DartLogger(__name__)


class NoOpEngine(object):
    def __init__(self, region, dart_host='localhost', dart_port=5000, dart_api_version=1):
        self.region = region
        self.dart = Dart(dart_host, dart_port, dart_api_version)

    def run(self):
        action_context = self.dart.engine_action_checkout(os.environ.get('DART_ACTION_ID'))
        action = action_context.action
        datastore = action_context.datastore

        state = ActionResultState.SUCCESS
        error_message = None
        try:
            sleep_seconds = datastore.data.args['action_sleep_time_in_seconds']
            _logger.info('sleeping for %s seconds...' % sleep_seconds)
            time.sleep(sleep_seconds)

            if action.data.action_type_name == NoOpActionTypes.action_that_fails.name:
                state = ActionResultState.FAILURE
                error_message = '%s failed as expected' % NoOpActionTypes.action_that_fails.name

            if action.data.action_type_name == NoOpActionTypes.consume_subscription.name:
                subscription_elements = self.dart.get_subscription_elements(action.id)
                _logger.info('consuming subscription, size = %s' % len(list(subscription_elements)))

        except Exception as e:
            state = ActionResultState.FAILURE
            error_message = e.message + '\n\n\n' + traceback.format_exc()

        finally:
            self.dart.engine_action_checkin(action.id, ActionResult(state, error_message))


class NoOpEngineTaskRunner(Tool):
    def __init__(self):
        super(NoOpEngineTaskRunner, self).__init__(_logger, configure_app_context=False)

    def run(self):
        NoOpEngine(**(self.dart_config['engines']['no_op_engine']['options'])).run()


if __name__ == '__main__':
    NoOpEngineTaskRunner().run()
