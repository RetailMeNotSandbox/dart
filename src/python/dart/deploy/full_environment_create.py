import argparse
import copy
import json
import logging

import boto3
from botocore.exceptions import ClientError

from dart.config.config import configuration, get_secrets_config, dart_root_relative_path
from dart.deploy.partial_environment_create import PartialEnvironmentCreateTool
from dart.util.rand import random_id
from dart.util.shell import call
from dart.util.config import _get_dart_host, _get_element

_logger = logging.getLogger(__name__)


class FullEnvironmentCreateTool(PartialEnvironmentCreateTool):
    """
    This tool:
      *  uses input_config_path to drive CloudFormation stack creation, etc
      *  writes an updated config file to output_config_s3_path
    """
    def __init__(self, environment_name, input_config_path, output_config_s3_path, dart_email_username,
                 stacks_to_skip):
        super(FullEnvironmentCreateTool, self).__init__(environment_name, input_config_path, output_config_s3_path,
                                                        dart_email_username, stacks_to_skip)

    def run(self):
        _logger.info('reading configuration...')
        output_config = copy.deepcopy(configuration(self.input_config_path, suppress_decryption=True))
        dart_host = _get_dart_host(output_config)
        _logger.info('setting up new dart full environment: %s' % dart_host)

        _logger.info('verifying s3 buckets do not exist')
        config_bucket_name = output_config['s3']['config_bucket']
        data_bucket_name = output_config['s3']['data_bucket']
        if 's3' not in self.stacks_to_skip:
            iequals = lambda s1, s2: s1.lower() == s2.lower()
            buckets = [b['Name'] for b in boto3.client('s3').list_buckets()['Buckets']]
            matches = [b for b in buckets if (iequals(b, config_bucket_name) or iequals(b, data_bucket_name))]
            if len(matches) > 0:
                raise Exception('s3 config and/or data bucket already exists!')

        _logger.info('creating initial stacks')
        aws_account_id = output_config['dart']['aws_account']
        replacements = {
            '{DART_REGION}': output_config['dart']['region'],
            '{DART_AWS_ACCOUNT}': aws_account_id,
            '{DART_QUEUE_PREFIX}': output_config['dart']['queue_prefix'],
            '{DART_CONFIG_BUCKET}': output_config['s3']['config_bucket'],
            '{DART_DATA_BUCKET}': output_config['s3']['data_bucket'],
        }
        iam_stack_name = self._create_stack('iam', output_config, replacements)
        sns_stack_name = self._create_stack('sns', output_config)

        _logger.info('waiting for stack completion')
        iam_outputs = self._wait_for_stack_completion_and_get_outputs(iam_stack_name, 7)
        sns_outputs = self._wait_for_stack_completion_and_get_outputs(sns_stack_name, 1)

        uds_inpf_role = _get_element(iam_outputs, 'OutputKey', 'UdsInstanceProfileRole')['OutputValue']
        uds_ec2_inpf = _get_element(iam_outputs, 'OutputKey', 'UdsEc2InstanceProfile')['OutputValue']
        uds_ec2_inpf_role = _get_element(iam_outputs, 'OutputKey', 'UdsEc2InstanceProfileRole')['OutputValue']
        ecs_container_inpf = _get_element(iam_outputs, 'OutputKey', 'EcsContainerInstanceProfile')['OutputValue']
        ecs_container_inpf_role = _get_element(iam_outputs, 'OutputKey', 'EcsContainerInstanceProfileRole')['OutputValue']
        ecs_service_role = _get_element(iam_outputs, 'OutputKey', 'EcsServiceRole')['OutputValue']
        sns_arn = sns_outputs[0]['OutputValue']

        _logger.info('updating configuration with sns arn')
        self._set_cfn_boto_param_value(output_config, 'logs', 'AlarmActions', sns_arn)

        _logger.info('updating configuration with subscription queue urls/arns')
        subscription_queue_arn, subscription_queue_url = self._ensure_queue_exists(output_config, 'subscription_queue')
        s3_params = output_config['cloudformation_stacks']['s3']['boto_args']['Parameters']
        _get_element(s3_params, 'ParameterKey', 'DartConfigBucket')['ParameterValue'] = config_bucket_name
        _get_element(s3_params, 'ParameterKey', 'DartDataBucket')['ParameterValue'] = data_bucket_name
        _get_element(s3_params, 'ParameterKey', 'SubscriptionQueueUrl')['ParameterValue'] = subscription_queue_url
        _get_element(s3_params, 'ParameterKey', 'SubscriptionQueueArn')['ParameterValue'] = subscription_queue_arn

        _logger.info('creating s3 and logs stacks')
        s3_stack_name = self._create_stack('s3', output_config)
        logs_stack_name = self._create_stack('logs', output_config)

        _logger.info('creating/updating kms key')
        with open(dart_root_relative_path(output_config['kms']['key_policy_template'])) as f:
            policy = json.load(f)
            kms_authorized_users = [self._role_arn(ecs_container_inpf_role, aws_account_id)]
            kms_authorized_users.extend(output_config['dart']['kms_key_user_arns'])
            policy['Statement'][0]['Principal']['AWS'] = 'arn:aws:iam::%s:root' % aws_account_id
            policy['Statement'][1]['Principal']['AWS'] = output_config['dart']['kms_key_admin_arns']
            policy['Statement'][2]['Principal']['AWS'] = kms_authorized_users
            policy['Statement'][3]['Principal']['AWS'] = kms_authorized_users
            policy_text = json.dumps(policy)
        kms_client = boto3.client('kms')
        key_arn = output_config['kms']['key_arn']
        if key_arn and key_arn != '...TBD...':
            kms_client.put_key_policy(KeyId=key_arn, PolicyName='default', Policy=policy_text)
        else:
            key_arn = kms_client.create_key(Policy=policy_text)['KeyMetadata']['Arn']
            alias = 'alias/dart-%s-secrets' % self.environment_name
            kms_client.create_alias(AliasName=alias, TargetKeyId=key_arn)

        _logger.info('updating configuration with kms key arn and secrets path, etc')
        output_config['engines']['redshift_engine']['options']['kms_key_arn'] = key_arn
        secrets_config = get_secrets_config(output_config)
        values = (config_bucket_name, self.environment_name)
        secrets_s3_path = 's3://%s/secrets/%s' % values
        secrets_config['secrets_s3_path'] = secrets_s3_path
        secrets_config['kms_key_arn'] = key_arn
        eng_cfg = output_config['engines']
        eng_cfg['redshift_engine']['options']['secrets_s3_path'] = secrets_s3_path
        output_config['dart']['s3_datastores_root'] = 's3://%s/datastores/%s' % values

        _logger.info('updating configuration with iam profiles/roles')
        output_config['engines']['emr_engine']['options']['instance_profile'] = uds_ec2_inpf
        output_config['engines']['emr_engine']['options']['service_role'] = uds_inpf_role
        output_config['engines']['dynamodb_engine']['options']['emr_instance_profile'] = uds_ec2_inpf
        output_config['engines']['dynamodb_engine']['options']['emr_service_role'] = uds_inpf_role
        self._set_cfn_boto_param_value(output_config, 'engine-taskrunner', 'IamInstanceProfile', ecs_container_inpf)
        self._set_cfn_boto_param_value(output_config, 'engine-worker', 'IamInstanceProfile', ecs_container_inpf)
        self._set_cfn_boto_param_value(output_config, 'subscription-worker', 'IamInstanceProfile', ecs_container_inpf)
        self._set_cfn_boto_param_value(output_config, 'trigger-worker', 'IamInstanceProfile', ecs_container_inpf)
        self._set_cfn_boto_param_value(output_config, 'web-internal', 'IamInstanceProfile', ecs_container_inpf)
        self._set_cfn_boto_param_value(output_config, 'web-internal', 'WebEcsServiceRoleName', ecs_service_role)
        self._set_cfn_boto_param_value(output_config, 'web', 'IamInstanceProfile', ecs_container_inpf)
        self._set_cfn_boto_param_value(output_config, 'web', 'WebEcsServiceRoleName', ecs_service_role)

        _logger.info('creating ECR repos')
        ecr_client = boto3.client('ecr')
        all_repo_names = [self._full_repo_name(r, output_config) for r in output_config['ecr']['repo_names']]
        existing_repo_names = []
        for repo_name in all_repo_names:
            try:
                ecr_client.describe_repositories(repositoryNames=[repo_name])
                existing_repo_names.append(repo_name)
            except ClientError as e:
                if e.response['Error']['Code'] == 'RepositoryNotFoundException':
                    continue
                raise e
        missing_repo_names = set(all_repo_names) - set(existing_repo_names)
        with open(dart_root_relative_path(output_config['ecr']['policy_template'])) as f:
            initial_policy = json.load(f)
            initial_policy['Statement'][0]['Principal']['AWS'] = output_config['dart']['ecr_authorized_user_arns']
            initial_policy_text = json.dumps(initial_policy)
        for repo_name in missing_repo_names:
            ecr_client.create_repository(repositoryName=repo_name)
            ecr_client.set_repository_policy(repositoryName=repo_name, policyText=initial_policy_text)

        _logger.info('updating ECR repo policies')
        ecr_policy_statement_sid = 'dart-%s-ecs-and-uds-permissions' % self.environment_name
        ecs_container_inpf_role_arn = self._role_arn(ecs_container_inpf_role, aws_account_id)
        uds_ec2_inpf_role_arn = self._role_arn(uds_ec2_inpf_role, aws_account_id)
        for repo_name in all_repo_names:
            policy = json.loads(ecr_client.get_repository_policy(repositoryName=repo_name)['policyText'])
            exists_index = None
            for i, statement in enumerate(policy['Statement']):
                if statement['Sid'] == ecr_policy_statement_sid:
                    exists_index = i
            if exists_index:
                policy['Statement'].pop(exists_index)
            policy['Statement'].append({
                'Sid': ecr_policy_statement_sid,
                'Effect': 'Allow',
                'Principal': {'AWS': [ecs_container_inpf_role_arn, uds_ec2_inpf_role_arn]},
                'Action': [
                    'ecr:GetDownloadUrlForLayer',
                    'ecr:BatchGetImage',
                    'ecr:BatchCheckLayerAvailability',
                    'ecr:GetAuthorizationToken'
                ]
            })
            policy_text = json.dumps(policy)
            ecr_client.set_repository_policy(repositoryName=repo_name, policyText=policy_text)

        _logger.info('updating configuration with docker image references')
        output_config['local_setup']['elasticmq_docker_image'] = self._docker_image('elasticmq', output_config)
        eng_cfg['no_op_engine']['docker_image'] = self._docker_image('engine-no_op', output_config)
        eng_cfg['emr_engine']['docker_image'] = self._docker_image('engine-emr', output_config)
        eng_cfg['emr_engine']['options']['impala_docker_repo_base_url'] = self._ecr_base_url(output_config)
        eng_cfg['dynamodb_engine']['docker_image'] = self._docker_image('engine-dynamodb', output_config)
        eng_cfg['dynamodb_engine']['options']['emr_impala_docker_repo_base_url'] = self._ecr_base_url(output_config)
        eng_cfg['redshift_engine']['docker_image'] = self._docker_image('engine-redshift', output_config)
        ew_image = self._docker_image('engine-worker', output_config)
        sw_image = self._docker_image('subscription-worker', output_config)
        tw_image = self._docker_image('trigger-worker', output_config)
        fl_image = self._docker_image('flask', output_config)
        nx_image = self._docker_image('nginx', output_config)
        cwl_image = self._docker_image('cloudwatchlogs', output_config)
        self._set_cfn_boto_param_value(output_config, 'engine-taskrunner', 'CloudWatchLogsDockerImage', cwl_image)
        self._set_cfn_boto_param_value(output_config, 'engine-worker', 'EngineWorkerDockerImage', ew_image)
        self._set_cfn_boto_param_value(output_config, 'engine-worker', 'CloudWatchLogsDockerImage', cwl_image)
        self._set_cfn_boto_param_value(output_config, 'subscription-worker', 'SubscriptionWorkerDockerImage', sw_image)
        self._set_cfn_boto_param_value(output_config, 'subscription-worker', 'CloudWatchLogsDockerImage', cwl_image)
        self._set_cfn_boto_param_value(output_config, 'trigger-worker', 'TriggerWorkerDockerImage', tw_image)
        self._set_cfn_boto_param_value(output_config, 'trigger-worker', 'CloudWatchLogsDockerImage', cwl_image)
        self._set_cfn_boto_param_value(output_config, 'web-internal', 'FlaskWorkerDockerImage', fl_image)
        self._set_cfn_boto_param_value(output_config, 'web-internal', 'NginxWorkerDockerImage', nx_image)
        self._set_cfn_boto_param_value(output_config, 'web-internal', 'CloudWatchLogsDockerImage', cwl_image)
        self._set_cfn_boto_param_value(output_config, 'web', 'FlaskWorkerDockerImage', fl_image)
        self._set_cfn_boto_param_value(output_config, 'web', 'NginxWorkerDockerImage', nx_image)
        self._set_cfn_boto_param_value(output_config, 'web', 'CloudWatchLogsDockerImage', cwl_image)

        _logger.info('updating configuration with DartConfig references')
        self._set_cfn_boto_param_value(output_config, 'engine-worker', 'DartConfig', self.output_config_s3_path)
        self._set_cfn_boto_param_value(output_config, 'subscription-worker', 'DartConfig', self.output_config_s3_path)
        self._set_cfn_boto_param_value(output_config, 'trigger-worker', 'DartConfig', self.output_config_s3_path)
        self._set_cfn_boto_param_value(output_config, 'web-internal', 'DartConfig', self.output_config_s3_path)
        self._set_cfn_boto_param_value(output_config, 'web', 'DartConfig', self.output_config_s3_path)
        eng_cfg['no_op_engine']['config'] = self.output_config_s3_path
        eng_cfg['emr_engine']['config'] = self.output_config_s3_path
        eng_cfg['dynamodb_engine']['config'] = self.output_config_s3_path
        eng_cfg['redshift_engine']['config'] = self.output_config_s3_path

        _logger.info('waiting for logs stack')
        logs_outputs = self._wait_for_stack_completion_and_get_outputs(logs_stack_name, 2)
        syslog_log_group_name = _get_element(logs_outputs, 'OutputKey', 'DartSyslog')['OutputValue']
        misc_log_group_name = _get_element(logs_outputs, 'OutputKey', 'DartMisc')['OutputValue']

        self._handle_docker_concerns(cwl_image, eng_cfg, misc_log_group_name, output_config, syslog_log_group_name)

        _logger.info('waiting for s3 stack')
        self._wait_for_stack_completion_and_get_outputs(s3_stack_name)

        self.create_partial(output_config)

        _logger.info('full environment created with config: %s, url: %s' % (self.output_config_s3_path, dart_host))

    def _handle_docker_concerns(self, cwl_image, eng_cfg, misc_log_group_name, output_config, syslog_log_group_name):
        if 'docker' in self.stacks_to_skip:
            _logger.info('skipping docker concerns')
            return

        _logger.info('configuring and building cloudwatch logs docker image (a special snowflake)')
        dart_root = dart_root_relative_path()
        r_id = random_id()
        values = (dart_root, r_id)
        call('cd %s && cd .. && git clone https://github.com/awslabs/ecs-cloudwatch-logs dart-cwl-%s' % values)
        docker_init = dart_root_relative_path('tools', 'docker', 'docker-local-init.sh')
        with open(dart_root_relative_path('aws', 'cloudwatch-logs', 'awslogs_template.conf')) as cwl_conf_template, \
                open(dart_root_relative_path('..', 'dart-cwl-%s/awslogs.conf' % r_id), mode='w') as cwl_conf:
            contents = cwl_conf_template.read()
            contents = contents.replace('{DART_LOG_GROUP_SYSLOG}', syslog_log_group_name)
            contents = contents.replace('{DART_LOG_GROUP_MISC}', misc_log_group_name)
            cwl_conf.write(contents)
        cwl_root = dart_root_relative_path('..', 'dart-cwl-%s' % r_id)
        call('source %s && cd %s && docker build -f Dockerfile -t %s .' % (docker_init, cwl_root, cwl_image))

        _logger.info('running grunt build')
        call('cd %s && grunt build' % dart_root_relative_path('src', 'python', 'dart', 'web', 'ui'))

        _logger.info('building other docker images')
        for repo_name in [rn for rn in output_config['ecr']['repo_names'] if not rn.endswith('cloudwatchlogs')]:
            version = eng_cfg['emr_engine']['options']['impala_version'] if 'impala' in repo_name else '1.0.0'
            docker_img = self._docker_image(repo_name, output_config, version=version)
            docker_file_suffix = repo_name.split('/')[-1]
            values = (docker_init, dart_root, docker_file_suffix, docker_img)
            call('source %s && cd %s && docker build -f tools/docker/Dockerfile-%s -t %s .' % values)

        _logger.info('pushing docker images')
        cmd = ('source %s && cd %s && $(aws ecr get-login)' % (docker_init, dart_root)) + ' && docker push %s'
        for repo_name in output_config['ecr']['repo_names']:
            version = eng_cfg['emr_engine']['options']['impala_version'] if 'impala' in repo_name else '1.0.0'
            call(cmd % self._docker_image(repo_name, output_config, version=version))

    def _set_cfn_boto_param_value(self, config, cfn_key, parameter_key, parameter_value):
        params = config['cloudformation_stacks'][cfn_key]['boto_args']['Parameters']
        _get_element(params, 'ParameterKey', parameter_key)['ParameterValue'] = parameter_value

    @staticmethod
    def _role_arn(role, aws_account_id):
        return 'arn:aws:iam::%s:role/%s' % (aws_account_id, role)

    @staticmethod
    def _full_repo_name(repo_name, dart_config):
        repo_prefix = dart_config['ecr']['repo_prefix']
        return repo_name if not repo_prefix else repo_prefix + '/' + repo_name

    @staticmethod
    def _ecr_base_url(dart_config):
        return '{aws_account}.dkr.ecr.{region}.amazonaws.com/{repo_prefix}'.format(
            aws_account=dart_config['dart']['aws_account'],
            region=dart_config['dart']['region'],
            repo_prefix=dart_config['ecr']['repo_prefix']
        )

    def _docker_image(self, repo_name, dart_config, version='1.0.0'):
        return '{aws_account}.dkr.ecr.{region}.amazonaws.com/{repo_name}:{version}'.format(
            aws_account=dart_config['dart']['aws_account'],
            region=dart_config['dart']['region'],
            repo_name=self._full_repo_name(repo_name, dart_config),
            version=version,
        )


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--environment-name', action='store', dest='environment_name', required=True)
    parser.add_argument('-i', '--input-config-path', action='store', dest='input_config_path', required=True)
    parser.add_argument('-o', '--output-config-s3-path', action='store', dest='output_config_s3_path', required=True)
    parser.add_argument('-u', '--dart-email-username', action='store', dest='dart_email_username', required=True)
    parser.add_argument('-s', '--stacks-to-skip', nargs='*', dest='stacks_to_skip')
    return parser.parse_args()


if __name__ == '__main__':
    args = _parse_args()
    FullEnvironmentCreateTool(
        args.environment_name,
        args.input_config_path,
        args.output_config_s3_path,
        args.dart_email_username,
        args.stacks_to_skip,
    ).run()
