from dart.util.logging_utils import DartLogger
import os
from dart.client.python.dart_client import Dart
from dart.config.config import configuration
from dart.engine.no_op.metadata import NoOpActionTypes
from dart.model.engine import Engine, EngineData

_logger = DartLogger(__name__)


def add_no_op_engine(config):
    engine_config = config['engines']['no_op_engine']
    opts = engine_config['options']
    dart = Dart(opts['dart_host'], opts['dart_port'], opts['dart_api_version'])
    assert isinstance(dart, Dart)

    _logger.info('saving no_op_engine')

    engine_id = None
    for e in dart.get_engines():
        if e.data.name == 'no_op_engine':
            engine_id = e.id

    ecs_task_definition = None if config['dart']['use_local_engines'] else {
        'family': 'dart-%s-no_op_engine' % config['dart']['env_name'],
        'containerDefinitions': [
            {
                'name': 'dart-no_op_engine',
                'cpu': 64,
                'memory': 256,
                'image': engine_config['docker_image'],
                'logConfiguration': {'logDriver': 'syslog'},
                'environment': [
                    {'name': 'DART_ROLE', 'value': 'worker:engine_no_op'},
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
        name='no_op_engine',
        description='Helps engineering test dart',
        options_json_schema={
            'type': 'object',
            'properties': {
                'action_sleep_time_in_seconds': {
                    'type': 'integer',
                    'minimum': 0,
                    'default': 5,
                    'description': 'The time to sleep for each action before completing'
                },
            },
            'additionalProperties': False,
            'required': [],
        },
        supported_action_types=[
            NoOpActionTypes.action_that_succeeds,
            NoOpActionTypes.action_that_fails,
            NoOpActionTypes.copy_hdfs_to_s3_action,
            NoOpActionTypes.load_dataset,
            NoOpActionTypes.consume_subscription
        ],
        ecs_task_definition=ecs_task_definition
    )))
    _logger.info('saved no_op_engine: %s' % e1.id)


if __name__ == '__main__':
    add_no_op_engine(configuration(os.environ['DART_CONFIG']))
