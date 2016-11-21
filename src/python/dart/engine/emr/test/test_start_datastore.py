from __future__ import absolute_import

import json
from mock import patch
import unittest

from dart.model.datastore import Datastore, DatastoreData
from dart.engine.emr.emr import EmrEngine
import dart.engine.emr.actions.start_datastore
from dart.engine.emr.actions.start_datastore import create_cluster, prepare_cluster_configurations


class TestStartDatastoreAction(unittest.TestCase):

    SPARK_DEFAULTS = {
        "Classification": "spark-defaults",
        "Properties": {
            "spark.executor.memory": "4G",
            "spark.executor.cores": "4"
        },
        "Configurations": []
    }

    SPARK_ENV = {
        "Classification": "spark-env",
        "Properties": {},
        "Configurations": [
            {
                "Classification": "export",
                "Properties": {
                    "PYSPARK_PYTHON": "/var/lib/rmn/xavier/xavier.runtime-current/bin/python"
                },
                "Configurations": []
            }
        ]
    }

    CONFIGURATION_OVERRIDES = [SPARK_DEFAULTS, SPARK_ENV]

    def test_prepare_cluster_configurations(self):
        file_url = prepare_cluster_configurations()
        self.assertTrue(file_url.startswith('file://'))
        self.assertTrue(file_url.endswith('start_configs.json'))

    def test_prepare_cluster_configurations_with_configuration_overrides(self):
        file_url = prepare_cluster_configurations(self.CONFIGURATION_OVERRIDES)
        self.check_extra_configs(file_url)

    def check_extra_configs(self, file_url):
        self.assertTrue(file_url.startswith('file://'))
        self.assertTrue(file_url.endswith('.json'))
        self.assertFalse(file_url.endswith('start_configs.json'))

        with open(file_url[7:], 'rt') as configs_file:
            configs = json.load(configs_file)

        configs_lookup = dict([(config['Classification'], config) for config in configs])

        spark_defaults = configs_lookup['spark-defaults']
        self.assertEqual(self.SPARK_DEFAULTS['Properties']['spark.executor.memory'],
                         spark_defaults['Properties']['spark.executor.memory'])
        self.assertEqual(self.SPARK_DEFAULTS['Properties']['spark.executor.cores'],
                         spark_defaults['Properties']['spark.executor.cores'])

        spark_env = configs_lookup['spark-env']
        self.assertEqual(self.SPARK_ENV, spark_env)

    @patch('dart.engine.emr.actions.start_datastore.call')
    def test_create_cluster_with_configuration_overrides(self, mock_call):
        mock_call.return_value = json.dumps({'ClusterId': '123'})

        datastore = Datastore()
        datastore.data = DatastoreData(name='test_create_cluster_with_configurations_datastore')
        datastore.data.args = {
            "data_to_freespace_ratio": 0.5,
            "dry_run": False,
            "instance_count": 1,
            "instance_type": "m3.xlarge",
            "release_label": "emr-4.8.2"
        }

        emr_engine = EmrEngine(
            ec2_keyname='xxx-yyy-ec2-key-pair-rpt',
            instance_profile='xxx-yyy-iam-rpt-1-UdsEc2InstanceProfile-1SIA38TXQ7OY1',
            service_role='xxx-yyy-iam-rpt-1-UdsInstanceProfileRole-FX98BLTMCK60',
            region='region',
            core_node_limit=30,
            impala_docker_repo_base_url='111111111111.wwww/xxx',
            impala_version='2.3.0',
            cluster_tags={
                'Name': 'xxx-yyy-uds',
                'Product': 'xxx',
                'Function': 'a-b',
                'Accounting': '222-1111111'
            },
            cluster_availability_zone='regionb',
            dart_host='somehost',
            dart_port=5000
        )

        instance_groups_args = [
            (1, 'MASTER', 'm3.xlarge', 'ON_DEMAND', 'master'),
            (1, 'CORE', 'm3.xlarge', 'ON_DEMAND', 'core'),
        ]

        create_cluster(bootstrap_actions_args=[],
                       cluster_name="test_create_cluster_with_configurations",
                       datastore=datastore,
                       emr_engine=emr_engine,
                       instance_groups_args=instance_groups_args,
                       configuration_overrides=self.CONFIGURATION_OVERRIDES)

        mock_call.assert_called_once()
        args = mock_call.call_args
        cmd_list = args[0][0].split(' ')
        pos = cmd_list.index('--configurations')
        file_url = cmd_list[pos+1]
        self.check_extra_configs(file_url)
