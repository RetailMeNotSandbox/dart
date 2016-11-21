import argparse
import copy
import logging
import os
import re
import boto3
from botocore.exceptions import ClientError
import requests
import sqlalchemy
import time
import yaml
from dart.config.config import configuration, get_secrets_config, dart_root_relative_path
from dart.deploy.deployment import DeploymentTool
from dart.deploy.put_stack import PutStack
from dart.engine.dynamodb.add_engine import add_dynamodb_engine
from dart.engine.emr.add_engine import add_emr_engine
from dart.engine.emr.add_sub_graphs import add_emr_engine_sub_graphs
from dart.engine.no_op.add_engine import add_no_op_engine
from dart.engine.no_op.add_sub_graphs import add_no_op_engine_sub_graphs
from dart.engine.redshift.add_engine import add_redshift_engine
from dart.engine.s3.add_engine import add_s3_engine
from dart.service.secrets import Secrets
from dart.model.exception import DartRequestException
from dart.util.config import _get_element, _get_dart_host
from retrying import retry

from dart.util.s3 import get_bucket_name, get_key_name

_logger = logging.getLogger(__name__)


class PartialEnvironmentCreateTool(DeploymentTool):
    """
    This tool:
      *  assumes that IAM, SNS, and CloudWatch Logs are already setup
      *  uses input_config_path to drive CloudFormation stack creation, etc
      *  writes an updated config file to output_config_s3_path

    The following are the stacks created/updated by this tool (in the order
    of how the script deploys them):
     - events
     - rds
     - elb
     - elb-internal
     - engine-taskrunner
     - web
     - web-internal
     - engine-worker
     - trigger-worker
     - subscription-worker
    """
    def __init__(self, environment_name, mode, input_config_path, output_config_s3_path, dart_email_username, stacks_to_skip):
        assert output_config_s3_path.startswith('s3://')
        self.environment_name = environment_name
        self.mode = mode
        self.input_config_path = input_config_path
        self.output_config_s3_path = output_config_s3_path
        self.dart_email_username = dart_email_username
        self.dart_email_password = os.environ['DART_EMAIL_PASSWORD']
        self.stacks_to_skip = set(stacks_to_skip or [])

    def run(self):
        _logger.info('reading configuration...')
        output_config = copy.deepcopy(configuration(self.input_config_path, suppress_decryption=True))
        dart_host = _get_dart_host(output_config)
        _logger.info('setting up new dart partial environment: %s' % dart_host)
        self.create_partial(output_config)
        _logger.info('partial environment created with config: %s, url: %s' % (self.output_config_s3_path, dart_host))

    def create_partial(self, output_config):
        _logger.info('updating configuration with trigger queue urls/arns')
        trigger_queue_arn, trigger_queue_url = self._ensure_queue_exists(output_config, 'trigger_queue')
        events_params = output_config['cloudformation_stacks']['events']['boto_args']['Parameters']
        _get_element(events_params, 'ParameterKey', 'TriggerQueueUrl')['ParameterValue'] = trigger_queue_url
        _get_element(events_params, 'ParameterKey', 'TriggerQueueArn')['ParameterValue'] = trigger_queue_arn

        _logger.info('creating initial stacks')
        events_stack_name = self._create_stack('events', self.mode, output_config)
        rds_stack_name = self._create_stack('rds', self.mode, output_config)
        elb_stack_name = self._create_stack('elb', self.mode, output_config)
        elb_int_stack_name = self._create_stack('elb-internal', self.mode, output_config)
        engine_taskrunner_stack_name = self._create_stack('engine-taskrunner', self.mode, output_config)

        _logger.info('waiting for stack completion')
        events_outputs = self._wait_for_stack_completion_and_get_outputs(events_stack_name, 1)
        rds_outputs = self._wait_for_stack_completion_and_get_outputs(rds_stack_name, 1)
        elb_outputs = self._wait_for_stack_completion_and_get_outputs(elb_stack_name, 1)
        elb_int_outputs = self._wait_for_stack_completion_and_get_outputs(elb_int_stack_name, 1)
        engine_taskrunner_outputs = self._wait_for_stack_completion_and_get_outputs(engine_taskrunner_stack_name, 1)

        _logger.info('updating configuration with new cloudwatch scheduled events sns topic name')
        sns_arn = events_outputs[0]['OutputValue']
        output_config['triggers']['scheduled']['cloudwatch_scheduled_events_sns_arn'] = sns_arn

        _logger.info('updating configuration with new rds endpoint and password')
        db_uri_secret_key = 'database-uri-%s' % self.environment_name
        output_config['flask']['SQLALCHEMY_DATABASE_URI'] = '!decrypt %s' % db_uri_secret_key
        secrets_config = get_secrets_config(output_config)
        secrets_service = Secrets(secrets_config['kms_key_arn'], secrets_config['secrets_s3_path'])
        rds_pwd = os.environ['DART_RDS_PASSWORD']
        rds_host = rds_outputs[0]['OutputValue']
        secrets_service.put(db_uri_secret_key, 'postgresql://dart:%s@%s:5432/dart' % (rds_pwd, rds_host))

        _logger.info('updating configuration with new elb name')
        web_params = output_config['cloudformation_stacks']['web']['boto_args']['Parameters']
        elb_name_param = _get_element(web_params, 'ParameterKey', 'WebEcsServiceLoadBalancerName')
        elb_name = elb_outputs[0]['OutputValue']
        elb_name_param['ParameterValue'] = elb_name

        _logger.info('updating configuration with new internal elb name')
        web_int_params = output_config['cloudformation_stacks']['web-internal']['boto_args']['Parameters']
        elb_int_name_param = _get_element(web_int_params, 'ParameterKey', 'WebEcsServiceLoadBalancerName')
        elb_int_name = elb_int_outputs[0]['OutputValue']
        elb_int_name_param['ParameterValue'] = elb_int_name

        _logger.info('updating configuration with new engine taskrunner ecs cluster name')
        output_config['dart']['engine_taskrunner_ecs_cluster'] = engine_taskrunner_outputs[0]['OutputValue']

        _logger.info('updating configuration with encrypted dart email username/password')
        mailer_options = output_config['email']['mailer']
        mailer_options['usr'] = '!decrypt email-username'
        mailer_options['pwd'] = '!decrypt email-password'
        secrets_service.put('email-username', self.dart_email_username)
        secrets_service.put('email-password', self.dart_email_password)

        _logger.info('uploading the output configuration to s3')
        body = yaml.dump(output_config, default_flow_style=False)
        body = re.sub(r"'!decrypt (.+?)'", r"!decrypt \1", body)
        body = re.sub(r"'!env (.+?)'", r"!env \1", body)
        body = re.sub(r"__DARTBANG__", r"!", body)
        body = re.sub(r"__DARTQUOTE__", r"'", body)
        body = re.sub(r"__DARTDOLLAR__", r"$", body)
        boto3.client('s3').put_object(
            Bucket=get_bucket_name(self.output_config_s3_path),
            Key=get_key_name(self.output_config_s3_path),
            Body=body
        )

        _logger.info('creating and waiting for web stacks')
        web_stack_name = self._create_stack('web', self.mode, output_config)
        web_internal_stack_name = self._create_stack('web-internal', self.mode, output_config)
        web_outputs = self._wait_for_stack_completion_and_get_outputs(web_stack_name, 2)
        self._wait_for_stack_completion_and_get_outputs(web_internal_stack_name)

        _logger.info('waiting for web ecs service to stabilize')
        cluster_name = _get_element(web_outputs, 'OutputKey', 'EcsClusterResourceName')['OutputValue']
        service_name = _get_element(web_outputs, 'OutputKey', 'WebEcsServiceResourceName')['OutputValue']
        boto3.client('ecs').get_waiter('services_stable').wait(cluster=cluster_name, services=[service_name])
        _logger.info('done')

        _logger.info('waiting for web app to attach to load balancer')
        self._wait_for_web_app(elb_name)
        time.sleep(5)

        _logger.info('initializing database schema')
        dart_host = _get_dart_host(output_config)
        response = requests.post('http://%s/admin/create_all' % dart_host)
        response.raise_for_status()
        time.sleep(5)

        _logger.info('creating database triggers')
        with open(dart_root_relative_path('src', 'database', 'triggers.sql')) as f:
            engine = sqlalchemy.create_engine('postgresql://dart:%s@%s:5432/dart' % (rds_pwd, rds_host))
            engine.execute(f.read())
        _logger.info('done')
        time.sleep(5)

        _logger.info('adding engines')
        self._with_retries(add_no_op_engine, output_config)
        self._with_retries(add_no_op_engine_sub_graphs, output_config)
        self._with_retries(add_emr_engine, output_config)
        self._with_retries(add_emr_engine_sub_graphs, output_config)
        self._with_retries(add_dynamodb_engine, output_config)
        self._with_retries(add_redshift_engine, output_config)
        self._with_retries(add_s3_engine, output_config)

        _logger.info('creating and waiting for remaining stacks')
        engine_worker_stack_name = self._create_stack('engine-worker', self.mode, output_config)
        trigger_worker_stack_name = self._create_stack('trigger-worker', self.mode, output_config)
        subscription_worker_stack_name = self._create_stack('subscription-worker', self.mode, output_config)
        self._wait_for_stack_completion_and_get_outputs(engine_worker_stack_name)
        self._wait_for_stack_completion_and_get_outputs(trigger_worker_stack_name)
        self._wait_for_stack_completion_and_get_outputs(subscription_worker_stack_name)

    def _create_stack(self, stack_name, mode, dart_config, template_body_replacements=None):
        stack = PutStack(mode, stack_name, 'v1', dart_config)
        if stack_name in self.stacks_to_skip:
            _logger.info('skipping stack creation: %s' % stack.dart_stack_name)
            return stack.dart_stack_name
        return stack.put_stack(template_body_replacements)

    @staticmethod
    def _get_queue_url(queue_name):
        sqs_client = boto3.client('sqs')
        try:
            return sqs_client.get_queue_url(QueueName=queue_name)['QueueUrl']
        except ClientError as e:
            if e.response['Error']['Code'] == 'AWS.SimpleQueueService.NonExistentQueue':
                return sqs_client.create_queue(QueueName=queue_name)['QueueUrl']
            raise e

    @staticmethod
    def _get_queue_arn(queue_url):
        sqs_client = boto3.client('sqs')
        response = sqs_client.get_queue_attributes(QueueUrl=queue_url, AttributeNames=['QueueArn'])
        return response['Attributes']['QueueArn']

    def _ensure_queue_exists(self, output_config, queue_name):
        queue_url = self._get_queue_url(output_config['sqs']['queue_names'][queue_name])
        queue_arn = self._get_queue_arn(queue_url)
        return queue_arn, queue_url

    @staticmethod
    def _retry_if_service_unavailable_error(exception):
        return isinstance(exception, DartRequestException) and exception.response.status_code == 503

    @staticmethod
    @retry(stop_max_attempt_number=10, wait_fixed=5000, retry_on_exception=_retry_if_service_unavailable_error)
    def _with_retries(function, *args, **kwargs):
        function(*args, **kwargs)


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--environment-name', action='store', dest='environment_name', required=True)
    parser.add_argument('-m', '--mode', action='store', dest='mode', required=True)
    parser.add_argument('-i', '--input-config-path', action='store', dest='input_config_path', required=True)
    parser.add_argument('-o', '--output-config-s3-path', action='store', dest='output_config_s3_path', required=True)
    parser.add_argument('-u', '--dart-email-username', action='store', dest='dart_email_username', required=True)
    parser.add_argument('-s', '--stacks-to-skip', nargs='*', dest='stacks_to_skip')
    return parser.parse_args()


if __name__ == '__main__':
    args = _parse_args()
    PartialEnvironmentCreateTool(
        args.environment_name,
        args.mode,
        args.input_config_path,
        args.output_config_s3_path,
        args.dart_email_username,
        args.stacks_to_skip,
    ).run()
