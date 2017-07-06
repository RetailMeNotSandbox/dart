import re
import json
from dart.model.action import Action
import logging
from itertools import groupby

_logger = logging.getLogger(__name__)


class AWS_Batch_Dag(object):
    def __init__(self, config_metadata, client, s3_client, action_batch_job_id_updater, subscription_element_service):
        """
        :param confiog_metadata: the dart.yaml config file as dictionary
        :param client: the batch voto3 client
        :param s3_client: the s3 boto3 client
        :param action_batch_job_id_updater: action_service.update_action_batch_job_id function
        """
        self.action_batch_job_id_updater = action_batch_job_id_updater

        # to discern between prd/stg images
        self.job_definition_suffix = config_metadata(['aws_batch', 'job_definition_suffix'])
        self.job_queue = config_metadata(['aws_batch', 'job_queue'])
        self.aws_default_region = config_metadata(['aws_batch', 'aws_default_region'])
        self.dart_config = config_metadata(['aws_batch', 'dart_config'])
        self.dart_url = config_metadata(['aws_batch', 'dart_url'])
        self.subscription_element_service = subscription_element_service

        # Where to place inputs/outputs to action from/to actions.  We will use the workflow_instance as "sub-bucket"
        self.s3_io_bucket = config_metadata(['aws_batch', 's3_io_bucket'])
        self.s3_io_prefix = config_metadata(['aws_batch', 's3_io_prefix'])

        # SNS to notify workflow completion and action completion
        self.sns_arn = config_metadata(['aws_batch', 'sns_arn'])

        self.client = client
        self.s3_client = s3_client  # TODO: for input/output
        _logger.info("AWS_Batch: using job_definition_suffix={0} and job_queue={1}".
                     format(self.job_definition_suffix, self.job_queue))

    def get_action_parent_jobs(self, oaction, order_idx_2_job_ids):
        dependency = []

        # If not the first action and no parents exist than the parent is the
        # job_id of action with order_idx == (current order_idx - 1)
        if not oaction.data.first_in_workflow and not oaction.data.parallelization_parents:
            dependency.append(order_idx_2_job_ids[int(oaction.data.order_idx) - 1])

        # If the action has parents, the parents should already exist (and be the previous job_id).
        if oaction.data.parallelization_parents:
            for parent in oaction.data.parallelization_parents:
                if order_idx_2_job_ids.get(int(parent)):
                    dependency.append(order_idx_2_job_ids[int(parent)])
                else:
                    _logger.error("Could not match current action (order_idx={0}) with a job_id of its parent order_idx {1}. parents={2}, order_idx_2_job_ids={3}".format(oaction.data.get('order_idx'), order_idx_2_job_ids.get(parent), oaction.data.get('parallelization_parents'), order_idx_2_job_ids))

        ret = [{'jobId': job} for job in dependency]
        return ret

    def generate_dag(self, single_ordered_wf_instance_actions, retries_on_failures, wf_attributes):
        if not single_ordered_wf_instance_actions:
            raise ValueError('Must receive actions in order to build a DAG. action={0}'.format(single_ordered_wf_instance_actions))

        #self.create_s3_bucket_for_workflow_io(wf_attributes['workflow_instance_id'])
        wf_attribs = self.create_workflow_attributes_dict(wf_attributes, retries_on_failures, self.sns_arn)
        all_previous_jobs = []  # will hold an array of jobIds, one per each action placed in Batch, so we can cancel if needed
        order_idx_2_job_ids = {}  # mapping of action to jobIds. Assumeing the jobs will be created in order, we can reach the parent when needed.
        for oaction in single_ordered_wf_instance_actions:
            dependency = self.get_action_parent_jobs(oaction, order_idx_2_job_ids)

            action_env = self.create_action_env_vars(action_id=oaction.id,
                                                     on_failure=oaction.data.on_failure,
                                                     step_id=oaction.data.workflow_action_id,
                                                     workflow_instance_id=wf_attribs['workflow_instance_id'],
                                                     idx=int(oaction.data.order_idx),
                                                     s3_io_bucket=self.s3_io_bucket,
                                                     s3_io_prefix=self.s3_io_prefix)
            try:
                if oaction.data.action_type_name == 'consume_subscription':
                    self.subscription_element_service.assign_subscription_elements(oaction)

                job_id = self.submit_job(wf_attribs, oaction.data.order_idx, oaction, len(single_ordered_wf_instance_actions)-1, dependency, action_env)

                #  job_id in action is needed so lookup_credentials(action) in action_runner.py would work correctly.
                self.action_batch_job_id_updater(oaction, job_id)
                order_idx_2_job_ids[int(oaction.data.order_idx)] = job_id
                all_previous_jobs.append(job_id)
                _logger.info("AWS_Batch: launched job={0}, wf_id={1}, wf_instance_id={2}".
                             format(job_id, wf_attribs['workflow_id'], wf_attribs['workflow_instance_id']))
            except Exception as err:
                _logger.error("AWS_Batch: DAG-err={0}".format(err))
                self.cancel_previous_jobs(all_previous_jobs)
                raise

        _logger.info("AWS_Batch: Done building workflow {0} with jobs: {1}".
                     format(wf_attribs['workflow_id'], all_previous_jobs))

    def submit_job(self, wf_attribs, idx, oaction, last_action_index, dependency, action_env):
        job_name = self.generate_job_name(wf_attribs['workflow_id'], oaction.data.order_idx, oaction.data.name, self.job_definition_suffix)
        _logger.info("AWS_Batch: job-name={0}, dependsOn={1}".format(job_name, dependency))

        # submit_job is sensitive to None value in env variables so we wrap them with str(..)
        input_env = json.dumps(self.generate_env_vars(wf_attribs, action_env, idx == 0, idx == last_action_index))
        response = self.client.submit_job(jobName=job_name,
                                          # SNS to notify workflow completion and action completion
                                          jobDefinition=self.get_latest_active_job_definition(oaction.data.engine_name, self.job_definition_suffix, self.client.describe_job_definitions),
                                          jobQueue=self.job_queue,
                                          dependsOn=dependency,
                                          containerOverrides={
                                              'environment': [
                                                  {'name': 'input_env', 'value': input_env}, # passing execution info to job
                                                  {'name': 'DART_ACTION_ID', 'value': str(oaction.id)},
                                                  {'name': 'DART_ACTION_USER_ID', 'value': str(oaction.data.user_id)},
                                                  {'name': 'DART_CONFIG', 'value': str(self.dart_config)},
                                                  {'name': 'DART_ROLE', 'value': "worker:{0}".format(oaction.data.engine_name)},  # An implicit convention
                                                  {'name': 'DART_URL', 'value': str(self.dart_url)}, # Used by abacus to access data lineage
                                                  {'name': 'AWS_DEFAULT_REGION', 'value': str(self.aws_default_region)}
                                              ]
                                          })
        _logger.info("AWS_Batch: response={0}".format(response))
        return response['jobId']

    @staticmethod
    def get_latest_active_job_definition(job_def_name, job_definition_suffix, describe_job_definitions_func):
        """ E.g.  job_def_name='redshift_engine' ==> we will get redshift_engine:3 (if 3 is the latest active version).
                  This will allow us to update the version used without changing the yaml files.
            Note: It's implicitly assumed the AWS Batch job definitions are named the same as the engine names in dart.

            >>> cls.get_latest_active_job_definition('road_runner', 'stg', describe_job_definitions_func_fail)
            Traceback (most recent call last):
            ...
            ValueError: No job matching road_runner_stg

            >>> cls.get_latest_active_job_definition('road-runner', 'prod', describe_job_definitions_func_success)
            'arn-3'
        """
        job_name = job_def_name
        if job_definition_suffix:
            job_name = "{0}_{1}".format(job_def_name, job_definition_suffix) # e.g. s3_engine_prd, or redshift_engine_stg
        _logger.info("AWS_batch: searching latest active job definition for name={0}".format(job_name))

        response = describe_job_definitions_func(jobDefinitionName=job_name, status='ACTIVE')
        _logger.info("AWS_batch: len(response['jobDefinitions'])={0}".format(len(response['jobDefinitions'])))

        if len(response['jobDefinitions']) > 0:
            arr = sorted(response['jobDefinitions'],
                         key=lambda x: int(x['revision']))  # the last item will be the highest (last) revision
            return arr[-1]['jobDefinitionArn']
        else:
            raise ValueError("No job matching {0}".format(job_name))

    @staticmethod
    def generate_job_name(workflow_id, order_idx, action_name, job_definition_suffix=''):
        """ Names should not exceed 50 characters or else cloudwatch logs creation will fail.

            :param workflow_id: the first part of the name is the workflow_id (which is not unique per job run).
            :param order_idx: The index of the action being run. Unique as lomg as the db action entries are not removed.
            :param action_name: action name may be truncate if total name exceed 50 characters. Also not unique.

            # no trimming
            >>> cls.generate_job_name('workflowid', 120, 'actionname', 'stg')
            'workflowid_120_actionname_stg'

            # trimmed action name
            >>> cls.generate_job_name('27_characters_long_workflow', 120, '25_characters_long_action', '')
            '27_characters_long_workflow_120_25_characters_long'
        """
        job_name = "{0}_{1}_{2}_{3}".format(workflow_id, order_idx, action_name.replace("-", "_"),job_definition_suffix)
        valid_characters_name = re.sub('[^a-zA-Z0-9_]', '', job_name) # job name valid pattern is: [^a-zA-Z0-9_]
        return valid_characters_name[0:50]

    @staticmethod
    def generate_env_vars(wf_attribs, action_env, is_first_action=False, is_last_action=False):
        """
            is_first_action/is_last_action in the workflow.  We notify upon start an end of workflow to update db status
            wf_attribs - dictionary of action data that will be handy to have on hand without queryig db and fir workflow identification
            action_env - dictionary of variable we need to run the actions
            Note: all inputs to submit_job(...) must strings (even int and booleans)

            :param wf_attributes: The workflow attributes that all job share (worfklow id, instance_id, datastore...)
            :param action_env: The action attributes that the job will get as env variables (along with wf_attribs)
            :param is_first_action: is first action in workflow
            :param is_last_action: is last action in workflow.


            >>> cls.generate_env_vars(wf_attribs={'workflow_id': 22}, action_env={}, is_first_action=True, is_last_action=False)
            [{'name': 'workflow_id', 'value': '22'}, {'name': 'is_first_action', 'value': 'True'}, {'name': 'is_last_action', 'value': 'False'}]

            >>> cls.generate_env_vars(wf_attribs={'workflow_id': 22}, action_env={'a': 'DD'}, is_first_action=True, is_last_action=False)
            [{'name': 'workflow_id', 'value': '22'}, {'name': 'a', 'value': 'DD'}, {'name': 'is_first_action', 'value': 'True'}, {'name': 'is_last_action', 'value': 'False'}]
        """
        env = [{'name': name, 'value': str(value)} for name, value in wf_attribs.iteritems()]
        env.extend([{'name': name, 'value': str(value)} for name, value in action_env.iteritems()])

        env.append({'name': 'is_first_action', 'value': str(is_first_action)})
        env.append({'name': 'is_last_action', 'value': str(is_last_action)})

        _logger.info("AWS_Batch: creating environment variables {0} for workflow={1}".
                     format(env, wf_attribs['workflow_id']))
        return env

    @staticmethod
    def create_workflow_attributes_dict( wf_attributes, retries_on_failures, sns_arn):
        """ This info will be sent to each job env and is mostly used for identifying workflows when querying batch
            and reduce the need to query the database.  This is effectively a mapping between job-id to action-id
            and we also know the workflow_instance_id (that needs to be updated)

            >>> cls.create_workflow_attributes_dict({'workflow_id': 456, 'workflow_instance_id': 334, 'datastore_id': 1}, 3, 'arn')['sns_arn']
            'arn'

            >>> cls.create_workflow_attributes_dict({'workflow_id': 456, 'workflow_instance_id': 334, 'datastore_id': 1}, 3, 'arn')['datastore_id']
            1

            >>> cls.create_workflow_attributes_dict({'workflow_id': 456, 'workflow_instance_id': 334, 'datastore_id': 1}, 3, 'arn')['retries_on_failures']
            3

        :param wf_attributes: The workflow attributes that all job share (worfklow id, instance_id, datastore...)
        :param retries_on_failures: This is a value per workflow that each job will receive.
        :param num_actions: how many total action there are (each will be launch in a batch-job)
        :param sns_arn: The arn used to notify change of status of an action.
        :return: a dictionary of all current wf_attributes augmented with sns_arn and retries_on_failures
        """
        wf_attributes = wf_attributes
        wf_attributes['sns_arn'] = sns_arn
        wf_attributes['retries_on_failures'] = retries_on_failures

        _logger.info("AWS_Batch: generate_dag, datastore={0}, workflow={1}, workflow_instance={2}".
                     format(wf_attributes['datastore_id'],
                            wf_attributes['workflow_id'],
                            wf_attributes['workflow_instance_id']))

        return wf_attributes


    @staticmethod
    def create_action_env_vars(action_id, on_failure, step_id, workflow_instance_id, idx, s3_io_bucket, s3_io_prefix):
        """ This info is unique to each action (the template action id it is associated with, the action_id, ...).
            An action will self regulate itself, thus it needs to know if to continue on failure and number of retries (a workflow attribute, not an action).
        :param action_id: The id of the action we will execute in the batch job.
        :param on_failure: Should this job continue if it fails or not
        :param step_id: The template action id this action is associated with (info purposes only)
        :param workflow_instance_id: to identify this job we set the workflow instance id as an env param.
        :param idx: the idx is used to set input/outputs to each action. (only relevant to 1-1 actions)
        :return: a dictionary of template_action_id, whether the action continue on failure, the action to run (id) and io for batch job.

        >>> cls.create_action_env_vars('XYZ987', 'CONTINUE', 'ABC123', '111AAA', 0, "bucket", "path")['current_step_id']
        'ABC123'

        >>> cls.create_action_env_vars('XYZ987', 'CONTINUE', 'ABC123', '111AAA', 0, "bucket", "path")['is_continue_on_failure']
        True

        >>> cls.create_action_env_vars('XYZ987', 'CONTINUE', 'ABC123', '111AAA', 0, "bucket", "path")['input_key']
        '111AAA_0.dat'

        >>> cls.create_action_env_vars('XYZ987', 'CONTINUE', 'ABC123', '111AAA', 0, "bucket", "path")['output_key']
        '111AAA_1.dat'
        """
        action_env = {
            "current_step_id": step_id,
            "is_continue_on_failure": (on_failure == "CONTINUE"),
            "ACTION_ID": action_id,
            "input_key": "{0}_{1}.dat".format(workflow_instance_id, idx),
            "output_key": "{0}_{1}.dat".format(workflow_instance_id, idx+1),  # This is the input to action with idx+1
            "s3_path": "{0}/{1}".format(s3_io_bucket, s3_io_prefix)
        }

        return action_env

    def cancel_previous_jobs(self, previous_jobs, reason="Failed to create all jobs in a dag"):
        for idx, job_id in enumerate(previous_jobs):
            response = None
            try:
                response = self.client.cancel_job(jobId=job_id, reason=reason)
            except Exception as err:
                _logger.error("AWS_Batch: Failed to cancel job={0} {1}/{2} jobs. err:{3}".
                              format(job_id, idx, len(previous_jobs), err))

            _logger.info("AWS_Batch: Canceling job #{0}={1}. metadata={2}".format(idx, job_id, response))

    # The bucket is self.s3_input_output/workflow_instance_id (each workflow_instance gets its own input/output folder)
    def create_s3_bucket_for_workflow_io(self, workflow_instance_id):
        try:
            response_key = self.s3_client.put_object(
                ACL='public-read-write',
                Bucket=self.s3_io_bucket,
                Key="{0}/{1}/".format(self.s3_io_prefix, workflow_instance_id)  # The folder unique to this workflow instance
            )
            _logger.info("AWS_Batch: created o folder for workflow {0}, response={1}".
                         format(workflow_instance_id, response_key))
        except Exception as err:
            _logger.error("AWS_Batch: S3 failed for workflow. base={0}/{1} , workflow_instance_id={2}, err: {3}".format(
                          self.s3_io_bucket, self.s3_io_prefix, workflow_instance_id, err))

if __name__ == "__main__":
    import doctest
    def fake_config(arr):
        return None

    def describe_job_definitions_func_fail(jobDefinitionName, status):
       return {'jobDefinitions': []}

    def describe_job_definitions_func_success(jobDefinitionName, status):
        return {'jobDefinitions': [{'revision': 2, 'jobDefinitionArn': 'arn-2'}, {'revision': 3, 'jobDefinitionArn': 'arn-3'}, {'revision': 1, 'jobDefinitionArn': 'arn-1'}]}

    class FakeData(object):
        def __init__(self):
            self.__dict__.update({'order_idx': 1, 'uparallelization_parents': []})

        def str(self):
            print self.order_idx

    class FakeAction(object):
        def __init__(self):
            self.__dict__.update({'data': FakeData()})

        def str(self):
            print self.data

    doctest.testmod(extraglobs={'cls': AWS_Batch_Dag(fake_config, None, None, None, None),
                                'FakeAction': FakeAction,
                                'describe_job_definitions_func_fail': describe_job_definitions_func_fail,
                                'describe_job_definitions_func_success': describe_job_definitions_func_success})
