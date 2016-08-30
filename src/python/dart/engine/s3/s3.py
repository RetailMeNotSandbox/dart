from dart.util.logging_utils import DartLogger
import os
import traceback

from dart.client.python.dart_client import Dart
from dart.engine.s3.actions.copy import copy
from dart.engine.s3.actions.data_check import data_check
from dart.engine.s3.metadata import S3ActionTypes
from dart.model.engine import ActionResultState, ActionResult
from dart.tool.tool_runner import Tool

_logger = DartLogger(__name__)


class S3Engine(object):
    def __init__(self, region, dart_host, dart_port, dart_api_version):
        self.region = region
        self.dart = Dart(dart_host, dart_port, dart_api_version)
        self._action_handlers = {
            S3ActionTypes.copy.name: copy,
            S3ActionTypes.data_check.name: data_check,
        }

    def run(self):
        action_context = self.dart.engine_action_checkout(os.environ.get('DART_ACTION_ID'))
        action = action_context.action
        datastore = action_context.datastore

        state = ActionResultState.SUCCESS
        error_message = None
        try:
            action_type_name = action.data.action_type_name
            _logger.info("*** S3Engine.run_action: %s", action_type_name)
            assert action_type_name in self._action_handlers, 'unsupported action: %s' % action_type_name
            handler = self._action_handlers[action_type_name]
            handler(self, datastore, action)

        except Exception as e:
            state = ActionResultState.FAILURE
            error_message = e.message + '\n\n\n' + traceback.format_exc()

        finally:
            self.dart.engine_action_checkin(action.id, ActionResult(state, error_message))


class S3EngineTaskRunner(Tool):
    def __init__(self):
        super(S3EngineTaskRunner, self).__init__(_logger, configure_app_context=False)

    def run(self):
        S3Engine(**(self.dart_config['engines']['s3_engine']['options'])).run()


if __name__ == '__main__':
    S3EngineTaskRunner().run()
