from dart.util.logging_utils import DartLogger
import os
import traceback

from dart.client.python.dart_client import Dart
from dart.engine.dynamodb.metadata import DynamoDBActionTypes
from dart.engine.dynamodb.actions.load_dataset import load_dataset
from dart.engine.dynamodb.actions.create_table import create_table
from dart.engine.dynamodb.actions.delete_table import delete_table
from dart.engine.emr.emr import EmrEngine
from dart.model.engine import ActionResult, ActionResultState
from dart.tool.tool_runner import Tool

_logger = DartLogger(__name__)


class DynamoDBEngine(object):
    def __init__(self, emr_ec2_keyname, emr_instance_profile, emr_service_role, emr_region, emr_core_node_limit,
                 emr_impala_docker_repo_base_url, emr_impala_version, emr_cluster_tags, emr_cluster_availability_zone,
                 dart_host, dart_port, dart_api_version=1, emr_release_label='emr-4.2.0',
                 emr_instance_type='m3.2xlarge'):

        self.emr_release_label = emr_release_label
        self.emr_instance_type = emr_instance_type
        self._action_handlers = {
            DynamoDBActionTypes.create_table.name: create_table,
            DynamoDBActionTypes.delete_table.name: delete_table,
            DynamoDBActionTypes.load_dataset.name: load_dataset,
        }
        self.emr_engine = EmrEngine(
            emr_ec2_keyname, emr_instance_profile, emr_service_role, emr_region, emr_core_node_limit,
            emr_impala_docker_repo_base_url, emr_impala_version, emr_cluster_tags, emr_cluster_availability_zone,
            dart_host, dart_port, dart_api_version
        )
        self.dart = Dart(dart_host, dart_port, dart_api_version)

    def run(self):
        action_context = self.dart.engine_action_checkout(os.environ.get('DART_ACTION_ID'))
        action = action_context.action
        datastore = action_context.datastore

        state = ActionResultState.SUCCESS
        consume_subscription_state = None
        error_message = None
        try:
            action_type_name = action.data.action_type_name
            assert action_type_name in self._action_handlers, 'unsupported action: %s' % action_type_name
            handler = self._action_handlers[action_type_name]
            handler(self, datastore, action)

        except Exception as e:
            state = ActionResultState.FAILURE
            error_message = e.message + '\n\n\n' + traceback.format_exc()

        finally:
            self.dart.engine_action_checkin(action.id, ActionResult(state, error_message, consume_subscription_state))


class DynamoDBEngineTaskRunner(Tool):
    def __init__(self):
        super(DynamoDBEngineTaskRunner, self).__init__(_logger, configure_app_context=False)

    def run(self):
        DynamoDBEngine(**(self.dart_config['engines']['dynamodb_engine']['options'])).run()


if __name__ == '__main__':
    DynamoDBEngineTaskRunner().run()
