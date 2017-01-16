import logging
import os
import traceback

from boto.emr import EmrConnection
from boto.regioninfo import RegionInfo

from dart.client.python.dart_client import Dart
from dart.engine.emr.actions.consume_subscription import consume_subscription
from dart.engine.emr.actions.copy_hdfs_to_s3 import copy_hdfs_to_s3
from dart.engine.emr.actions.load_dataset import load_dataset
from dart.engine.emr.actions.run_hive_script import run_hive_script
from dart.engine.emr.actions.run_impala_script import run_impala_script
from dart.engine.emr.actions.run_pyspark_script import run_pyspark_script
from dart.engine.emr.actions.start_datastore import start_datastore
from dart.engine.emr.actions.terminate_datastore import terminate_datastore
from dart.engine.emr.exception.exception import ActionFailedButConsumeSuccessfulException
from dart.engine.emr.metadata import EmrActionTypes
from dart.model.engine import ActionResult, ActionResultState, ConsumeSubscriptionResultState
from dart.tool.tool_runner import Tool

_logger = logging.getLogger(__name__)


class EmrEngine(object):
    def __init__(self, ec2_keyname, instance_profile, service_role, subnet_id, region, core_node_limit,
                 impala_docker_repo_base_url, impala_version, cluster_tags, dart_host, dart_port, dart_api_version=1):

        self._action_handlers = {
            EmrActionTypes.start_datastore.name: start_datastore,
            EmrActionTypes.terminate_datastore.name: terminate_datastore,
            EmrActionTypes.load_dataset.name: load_dataset,
            EmrActionTypes.consume_subscription.name: consume_subscription,
            EmrActionTypes.run_hive_script_action.name: run_hive_script,
            EmrActionTypes.run_impala_script_action.name: run_impala_script,
            EmrActionTypes.run_pyspark_script_action.name: run_pyspark_script,
            EmrActionTypes.copy_hdfs_to_s3_action.name: copy_hdfs_to_s3,
        }
        self._region = RegionInfo(self, region, 'elasticmapreduce.%s.amazonaws.com' % region) if region else None
        self._conn = None
        self.ec2_keyname = ec2_keyname
        self.core_node_limit = core_node_limit
        self.instance_profile = instance_profile
        self.service_role = service_role
        self.subnet_id = subnet_id
        self.cluster_tags = cluster_tags
        self.impala_docker_repo_base_url = impala_docker_repo_base_url
        self.impala_version = impala_version
        self.dart = Dart(dart_host, dart_port, dart_api_version)

    @property
    def conn(self):
        if self._conn:
            return self._conn
        self._conn = EmrConnection(region=self._region)
        return self._conn

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

        except ActionFailedButConsumeSuccessfulException as e:
            state = ActionResultState.FAILURE
            consume_subscription_state = ConsumeSubscriptionResultState.SUCCESS
            error_message = e.message + '\n\n\n' + traceback.format_exc()

        except Exception as e:
            state = ActionResultState.FAILURE
            error_message = e.message + '\n\n\n' + traceback.format_exc()

        finally:
            self.dart.engine_action_checkin(action.id, ActionResult(state, error_message, consume_subscription_state))


class EmrEngineTaskRunner(Tool):
    def __init__(self):
        super(EmrEngineTaskRunner, self).__init__(_logger, configure_app_context=False)

    def run(self):
        EmrEngine(**(self.dart_config['engines']['emr_engine']['options'])).run()


if __name__ == '__main__':
    EmrEngineTaskRunner().run()
