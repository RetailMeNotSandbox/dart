from dart.util.logging_utils import DartLogger
import os
from dart.client.python.dart_client import Dart
from dart.config.config import configuration
from dart.engine.emr.metadata import EmrActionTypes
from dart.model.engine import Engine, EngineData

_logger = DartLogger(__name__)


def add_emr_engine(config):
    engine_config = config['engines']['emr_engine']
    opts = engine_config['options']
    dart = Dart(opts['dart_host'], opts['dart_port'], opts['dart_api_version'])
    assert isinstance(dart, Dart)

    _logger.info('saving emr_engine')

    engine_id = None
    for e in dart.get_engines():
        if e.data.name == 'emr_engine':
            engine_id = e.id

    ecs_task_definition = None if config['dart']['use_local_engines'] else {
        'family': 'dart-%s-emr_engine' % config['dart']['env_name'],
        'containerDefinitions': [
            {
                'name': 'dart-emr_engine',
                'cpu': 64,
                'memory': 256,
                'image': engine_config['docker_image'],
                'logConfiguration': {'logDriver': 'syslog'},
                'environment': [
                    {'name': 'DART_ROLE', 'value': 'worker:engine_emr'},
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
        name='emr_engine',
        description='For EMR clusters that use Hive, Impala, Spark, etc.',
        options_json_schema={
            'type': 'object',
            'properties': {
                'release_label': {'type': 'string', 'pattern': '^emr-[0-9].[0-9].[0-9]+$', 'default': 'emr-4.2.0', 'description': 'desired EMR release label'},
                'instance_type': {'readonly': True, 'type': ['string', 'null'], 'default': 'm3.2xlarge', 'description': 'The ec2 instance type of master/core nodes'},
                'instance_count': {'type': ['integer', 'null'], 'default': None, 'minimum': 1, 'maximum': 50, 'description': 'The total number of nodes in this cluster (overrides data_to_freespace_ratio)'},
                'data_to_freespace_ratio': {'type': ['number', 'null'], 'default': 0.5, 'minimum': 0.0, 'maximum': 1.0, 'description': 'Desired ratio of HDFS data/free-space'},
                'dry_run': {'type': ['boolean', 'null'], 'default': False, 'description': 'write extra_data to actions, but do not actually run'},
            },
            'additionalProperties': False,
            'required': ['release_label'],
        },
        supported_action_types=[
            EmrActionTypes.start_datastore,
            EmrActionTypes.terminate_datastore,
            EmrActionTypes.load_dataset,
            EmrActionTypes.consume_subscription,
            EmrActionTypes.run_hive_script_action,
            EmrActionTypes.run_impala_script_action,
            EmrActionTypes.run_pyspark_script_action,
            EmrActionTypes.copy_hdfs_to_s3_action
        ],
        ecs_task_definition=ecs_task_definition
    )))
    _logger.info('saved emr_engine: %s' % e1.id)


if __name__ == '__main__':
    add_emr_engine(configuration(os.environ['DART_CONFIG']))
