from dart.util.logging_utils import DartLogger
import os
import random
import traceback

from dart.client.python.dart_client import Dart
from dart.engine.redshift.actions.data_check import data_check
from dart.engine.redshift.actions.copy_to_s3 import copy_to_s3
from dart.engine.redshift.actions.consume_subscription import consume_subscription
from dart.engine.redshift.actions.create_snapshot import create_snapshot
from dart.engine.redshift.actions.load_dataset import load_dataset
from dart.engine.redshift.actions.start_datastore import start_datastore
from dart.engine.redshift.actions.stop_datastore import stop_datastore
from dart.engine.redshift.actions.execute_sql import execute_sql
from dart.engine.redshift.metadata import RedshiftActionTypes
from dart.model.engine import ActionResultState, ActionResult
from dart.service.secrets import Secrets
from dart.tool.tool_runner import Tool

_logger = DartLogger(__name__)


class RedshiftEngine(object):
    def __init__(self, kms_key_arn, secrets_s3_path, vpc_subnet, security_group_ids,
                 region, availability_zones, publicly_accessible, cluster_tags,
                 dart_host, dart_port, dart_api_version=1):

        self.dart = Dart(dart_host, dart_port, dart_api_version)
        self._action_handlers = {
            RedshiftActionTypes.start_datastore.name: start_datastore,
            RedshiftActionTypes.stop_datastore.name: stop_datastore,
            RedshiftActionTypes.execute_sql.name: execute_sql,
            RedshiftActionTypes.load_dataset.name: load_dataset,
            RedshiftActionTypes.consume_subscription.name: consume_subscription,
            RedshiftActionTypes.copy_to_s3.name: copy_to_s3,
            RedshiftActionTypes.create_snapshot.name: create_snapshot,
            RedshiftActionTypes.data_check.name: data_check,
        }
        self.vpc_subnet = vpc_subnet
        self.availability_zones = availability_zones
        self.publicly_accessible = publicly_accessible
        self.security_group_ids = security_group_ids
        self.cluster_tags = cluster_tags
        self.region = region
        self.secrets = Secrets(kms_key_arn, secrets_s3_path)

    def random_availability_zone(self):
        return self.availability_zones[random.randint(0, len(self.availability_zones) - 1)]

    def run(self):
        action_context = self.dart.engine_action_checkout(os.environ.get('DART_ACTION_ID'))
        action = action_context.action
        datastore = action_context.datastore

        state = ActionResultState.SUCCESS
        error_message = None
        try:
            action_type_name = action.data.action_type_name
            _logger.info("**** RedshiftEngine.run_action: %s", action_type_name)
            assert action_type_name in self._action_handlers, 'unsupported action: %s' % action_type_name
            handler = self._action_handlers[action_type_name]
            handler(self, datastore, action)

        except Exception as e:
            state = ActionResultState.FAILURE
            error_message = e.message + '\n\n\n' + traceback.format_exc()

        finally:
            self.dart.engine_action_checkin(action.id, ActionResult(state, error_message))


class RedshiftEngineTaskRunner(Tool):
    def __init__(self):
        super(RedshiftEngineTaskRunner, self).__init__(_logger, configure_app_context=False)

    def run(self):
        RedshiftEngine(**(self.dart_config['engines']['redshift_engine']['options'])).run()


if __name__ == '__main__':
    RedshiftEngineTaskRunner().run()
