from dart.util.logging_utils import DartLogger
import os

from dart.client.python.dart_client import Dart
from dart.config.config import configuration
from dart.engine.s3.metadata import S3ActionTypes
from dart.model.engine import Engine, EngineData

_logger = DartLogger(__name__)


def add_s3_engine(config):
    engine_config = config['engines']['s3_engine']
    opts = engine_config['options']
    dart = Dart(opts['dart_host'], opts['dart_port'], opts['dart_api_version'])
    assert isinstance(dart, Dart)

    _logger.info('saving s3 engine')

    engine_id = None
    for e in dart.get_engines():
        if e.data.name == 's3_engine':
            engine_id = e.id

    ecs_task_definition = None if config['dart']['use_local_engines'] else {
        'family': 'dart-%s-s3_engine' % config['dart']['env_name'],
        'containerDefinitions': [
            {
                'name': 'dart-s3_engine',
                'cpu': 64,
                'memory': 256,
                'image': engine_config['docker_image'],
                'logConfiguration': {'logDriver': 'syslog'},
                'environment': [
                    {'name': 'DART_ROLE', 'value': 'worker:engine_s3'},
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
        name='s3_engine',
        description='For S3 operations',
        options_json_schema={},
        supported_action_types=[
            S3ActionTypes.copy,
            S3ActionTypes.data_check,
        ],
        ecs_task_definition=ecs_task_definition
    )))
    _logger.info('Saved s3_engine: %s' % e1.id)

if __name__ == '__main__':
    add_s3_engine(configuration(os.environ['DART_CONFIG']))
