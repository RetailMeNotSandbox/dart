from dart.util.logging_utils import DartLogger
import os
from dart.client.python.dart_client import Dart
from dart.config.config import configuration
from dart.engine.redshift.metadata import RedshiftActionTypes
from dart.model.engine import Engine, EngineData

_logger = DartLogger(__name__)


def add_redshift_engine(config):
    engine_config = config['engines']['redshift_engine']
    opts = engine_config['options']
    dart = Dart(opts['dart_host'], opts['dart_port'], opts['dart_api_version'])
    assert isinstance(dart, Dart)

    _logger.info('saving redshift_engine')

    engine_id = None
    for e in dart.get_engines():
        if e.data.name == 'redshift_engine':
            engine_id = e.id

    ecs_task_definition = None if config['dart']['use_local_engines'] else {
        'family': 'dart-%s-redshift_engine' % config['dart']['env_name'],
        'containerDefinitions': [
            {
                'name': 'dart-redshift_engine',
                'cpu': 64,
                'memory': 256,
                'image': engine_config['docker_image'],
                'logConfiguration': {'logDriver': 'syslog'},
                'environment': [
                    {'name': 'DART_ROLE', 'value': 'worker:engine_redshift'},
                    {'name': 'DART_CONFIG', 'value': engine_config['config']},
                    {'name': 'AWS_DEFAULT_REGION', 'value': opts['region']}
                ],
                'mountPoints': [
                    {
                        'containerPath': '/mnt/ecs_agent_data',
                        'sourceVolume': 'ecs-agent-data',
                        'readOnly': True
                    }
                ],
            }
        ],
        'volumes': [
            {
                'host': {'sourcePath': '/var/lib/ecs/data'},
                'name': 'ecs-agent-data'
            }
        ],
    }

    e1 = dart.save_engine(Engine(id=engine_id, data=EngineData(
        name='redshift_engine',
        description='For Redshift clusters',
        options_json_schema={
            'type': 'object',
            'properties': {
                'node_type': {
                    'type': 'string',
                    'default': 'ds2.xlarge',
                    'enum': ['ds1.xlarge', 'ds1.8xlarge', 'ds2.xlarge', 'ds2.8xlarge', 'dc1.large', 'dc1.8xlarge'],
                    'description': 'the type of each node'
                },
                'nodes': {
                    'type': 'integer',
                    'default': 2,
                    'minimum': 2,
                    'maximum': 50,
                    'description': 'the number of nodes in this cluster'
                },
                'master_user_name': {
                    'type': ['string', 'null'],
                    'default': 'admin',
                    'minLength': 1,
                    'maxLength': 128,
                    'pattern': '^[a-zA-Z]+[a-zA-Z0-9]*$',
                    'description': 'the master user name for this redshift cluster'
                },
                'master_user_password': {
                    'type': 'string',
                    'default': 'passw0rD--CHANGE-ME!',
                    'minLength': 8,
                    'maxLength': 64,
                    'pattern': '(?=.*\d)(?=.*[a-z])(?=.*[A-Z])(?!.*[\'"\/@\s])',
                    'x-dart-secret': True,
                    'description': 'the master user password for this redshift cluster (hidden and ignored after'
                                   + ' initial save), see AWS docs for password requirements'
                },
                'master_db_name': {
                    'type': ['string', 'null'],
                    "default": 'dart',
                    'minLength': 1,
                    'maxLength': 64,
                    'pattern': '^[a-z]+$',
                    'description': 'the master database name for this redshift cluster'
                },
                'cluster_identifier': {
                    'type': ['string', 'null'],
                    'default': None,
                    'minLength': 1,
                    'maxLength': 63,
                    'pattern': '^[a-zA-Z0-9-]*$',
                    'description': 'this overrides the auto-generated dart cluster_identifier'
                },
                'preferred_maintenance_window': {
                    'type': 'string',
                    'default': 'sat:03:30-sat:04:00',
                    'description': 'UTC time when automated cluster maintenance can occur'
                },
                'snapshot_retention': {
                    'type': 'integer',
                    'default': 2,
                    'minimum': 1,
                    'maximum': 10,
                    'description': 'the maximum number of snapshots to keep, older ones will be deleted'
                },
            },
            'additionalProperties': False,
            'required': ['master_user_password']
        },
        supported_action_types=[
            RedshiftActionTypes.start_datastore,
            RedshiftActionTypes.stop_datastore,
            RedshiftActionTypes.execute_sql,
            RedshiftActionTypes.load_dataset,
            RedshiftActionTypes.consume_subscription,
            RedshiftActionTypes.copy_to_s3,
            RedshiftActionTypes.create_snapshot,
            RedshiftActionTypes.data_check,
        ],
        ecs_task_definition=ecs_task_definition
    )))
    _logger.info('saved redshift_engine: %s' % e1.id)


if __name__ == '__main__':
    add_redshift_engine(configuration(os.environ['DART_CONFIG']))
