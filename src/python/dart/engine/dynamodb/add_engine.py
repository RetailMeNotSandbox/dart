from dart.util.logging_utils import DartLogger
import os
from dart.client.python.dart_client import Dart
from dart.config.config import configuration
from dart.engine.dynamodb.metadata import DynamoDBActionTypes
from dart.model.engine import Engine, EngineData

_logger = DartLogger(__name__)


def add_dynamodb_engine(config):
    engine_config = config['engines']['dynamodb_engine']
    opts = engine_config['options']
    dart = Dart(opts['dart_host'], opts['dart_port'], opts['dart_api_version'])
    assert isinstance(dart, Dart)

    _logger.info('saving dynamodb_engine')

    engine_id = None
    for e in dart.get_engines():
        if e.data.name == 'dynamodb_engine':
            engine_id = e.id

    ecs_task_definition = None if config['dart']['use_local_engines'] else {
        'family': 'dart-%s-dynamodb_engine' % config['dart']['env_name'],
        'containerDefinitions': [
            {
                'name': 'dart-dynamodb_engine',
                'cpu': 64,
                'memory': 256,
                'image': engine_config['docker_image'],
                'logConfiguration': {'logDriver': 'syslog'},
                'environment': [
                    {'name': 'DART_ROLE', 'value': 'worker:engine_dynamodb'},
                    {'name': 'DART_CONFIG', 'value': engine_config['config']},
                    {'name': 'AWS_DEFAULT_REGION', 'value': opts['emr_region']}
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
        name='dynamodb_engine',
        description='For DynamoDB tables',
        options_json_schema={
            'type': 'object',
            'properties': {
                'dataset_id': {'type': 'string', 'description': 'The id of the dataset on which the table is based'},
                'target_table_name': {'type': ['string', 'null'], 'default': None, 'pattern': '^[a-zA-Z0-9_]+$', 'description': 'overrides dataset setting'},
                'target_distribution_key': {'type': ['string', 'null'], 'default': None, 'pattern': '^[a-zA-Z0-9_]+$', 'description': 'overrides dataset setting'},
                'target_sort_key': {'type': ['string', 'null'], 'default': None, 'pattern': '^[a-zA-Z0-9_]+$', 'description': 'overrides dataset setting'},
            },
            'additionalProperties': False,
            'required': ['dataset_id'],
        },
        supported_action_types=[
            DynamoDBActionTypes.create_table,
            DynamoDBActionTypes.delete_table,
            DynamoDBActionTypes.load_dataset,
        ],
        ecs_task_definition=ecs_task_definition
    )))
    _logger.info('saved dynamodb_engine: %s' % e1.id)


if __name__ == '__main__':
    add_dynamodb_engine(configuration(os.environ['DART_CONFIG']))
