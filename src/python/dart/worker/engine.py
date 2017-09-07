import json
import logging
import logging.config
import os
from pydoc import locate
import time
import traceback
from datetime import datetime
from itertools import islice
from multiprocessing import Process

import re
import boto3
from dateutil.tz import tzutc

from dart.context.database import db
from dart.message.trigger_proxy import TriggerProxy
from dart.model.action import ActionState
from dart.model.datastore import DatastoreState
from dart.model.exception import DartConditionalUpdateFailedException
from dart.model.mutex import Mutexes
from dart.service.action import ActionService
from dart.service.datastore import DatastoreService
from dart.service.engine import EngineService
from dart.service.mutex import db_mutex
from dart.tool.tool_runner import Tool
from dart.worker.worker import Worker

_logger = logging.getLogger(__name__)


class EngineWorker(Tool):
    def __init__(self):
        super(EngineWorker, self).__init__(_logger)
        self._engine_service = self.app_context.get(EngineService)
        self._action_service = self.app_context.get(ActionService)
        self._datastore_service = self.app_context.get(DatastoreService)
        self._trigger_proxy = self.app_context.get(TriggerProxy)
        self._sleep_seconds = 0.7
        self._counter = Counter(transition_queued=1, transition_stale=85, transition_orphaned=60, scale_down=120)

        self.batch_queue = self.dart_config['aws_batch'].get('job_queue') # The AWS batch queue we place the jobs in
        self.batch_job_suffix = self.dart_config['aws_batch'].get('job_definition_suffix')  # e.g. stg/prd
        self.sns_arn = self.dart_config['aws_batch'].get('sns_arn')  # different arn for stg/prd

    def run(self):
        time.sleep(self._sleep_seconds)
        self._counter.increment()

        if self._counter.is_ready('transition_queued'):
            self._transition_queued_actions_to_pending()

        if self._counter.is_ready('transition_stale'):
            self._transition_stale_pending_actions_to_queued()

    def _transition_queued_actions_to_pending(self):
        _logger.info('transitioning queued actions to pending')
        action_service = self._action_service
        engine_service = self._engine_service
        datastore_service = self._datastore_service
        assert isinstance(action_service, ActionService)
        assert isinstance(engine_service, EngineService)
        assert isinstance(datastore_service, DatastoreService)
        queued_actions = action_service.find_actions(states=[ActionState.QUEUED])
        for action in queued_actions:
            try:
                datastore = datastore_service.get_datastore(action.data.datastore_id, raise_when_missing=False)
                if not datastore or datastore.data.state != DatastoreState.ACTIVE:
                    continue

                states = [ActionState.PENDING, ActionState.RUNNING, ActionState.FINISHING]
                action_count = self._action_service.find_action_count(datastore.id, states)
                if action_count >= datastore.data.concurrency:
                    _logger.info('datastore (id=%s) has reached max concurrency' % datastore.id)
                    continue

                # conditionally updating queued actions as pending allows multiple concurrent engine workers if needed
                action_service.update_action_state(
                    action=action,
                    state=ActionState.PENDING,
                    error_message=action.data.error_message,
                    conditional=lambda a: a.data.state == ActionState.QUEUED
                )

                engine = engine_service.get_engine_by_name(action.data.engine_name)

                # our best granualrity of a user_id to identifu who is running this workflow's action.
                datastore_user_id = datastore.data.user_id if hasattr(datastore.data, 'user_id') else 'anonymous'
                if self.dart_config['dart'].get('use_local_engines'):
                    config = self.dart_config['engines'][engine.data.name]
                    engine_instance = locate(config['path'])(**config.get('options', {}))
                    self._launch_in_memory_engine(engine, engine_instance, action, datastore_user_id)
                    # empty string allows differentiation from null, yet is still falsey
                    action_service.update_action_batch_job_id(action, '')

                elif engine.data.ecs_task_definition_arn:
                    batch_job_id = self._try_run_task(action, datastore_user_id)
                    if batch_job_id:
                        action_service.update_action_batch_job_id(action, batch_job_id)
                    else:
                        # no batch job-id means there isn't enough capacity at the moment, so try again later
                        action_service.update_action_state(action, ActionState.QUEUED, error_message=action.data.error_message)

                else:
                    msg = 'engine %s has no ecs_task_definition and local engines are not allowed'
                    raise Exception(msg % engine.data.name)

            except DartConditionalUpdateFailedException:
                # another engine worker picked it up
                continue

            except Exception as e:
                error_message = e.message + '\n\n\n' + traceback.format_exc()
                _logger.error('error transitioning action (id=%s) to PENDING: %s' % (action.id, error_message))

            finally:
                db.session.rollback()

    def _get_latest_active_job_definition(self, job_def_name):
        """ E.g.  job_def_name='redshift_engine_prd' ==> we will get redshift_engine_prd:3 (if 3 is the latest active version).
                  This will allow us to update the version used without changing the yaml files.
            Note: It is implicitly assumed that the AWS Batch job definitions are named the same as the engine names in dart.
        """
        def_name = "{0}_{1}".format(job_def_name, self.batch_job_suffix) # e.g. s3_engine_prd, or redshift_engine_stg
        _logger.info("AWS_batch: searching latest active job definition for name={0}".format(def_name))

        response = boto3.client('batch').describe_job_definitions(jobDefinitionName=def_name, status='ACTIVE')
        _logger.info("AWS_batch: len(response['jobDefinitions'])={0}".format(len(response['jobDefinitions'])))

        if len(response['jobDefinitions']) > 0:
            arr = sorted(response['jobDefinitions'],
                         key=lambda x: int(x['revision']))  # the last item will be the highest (last) revision
            return arr[-1]['jobDefinitionArn']
        else:
            _logger.error("No job matching {0}".format(def_name))
            return None

    def _generate_job_name(self, workflow_id, order_idx, action_name):
        """ Names should not exceed 50 characters or else cloudwatch logs will fail. """
        job_name = "{0}_{1}_{2}_{3}".format(workflow_id, order_idx, action_name.replace("-", "_"), self.batch_job_suffix)
        valid_characters_name = re.sub('[^a-zA-Z0-9_]', '', job_name) # job name valid pattern is: [^a-zA-Z0-9_]
        return valid_characters_name[0:50]

    @db_mutex(Mutexes.START_ENGINE_TASK)
    def _try_run_task(self, action, datastore_user_id):
        msg = 'AWS_Batch: trying to run Batch job workflow_id={0}, order_idx={1}, action_name={2}'
        _logger.info(msg.format(action.data.workflow_id, action.data.order_idx, action.data.name))

        job_name = self._generate_job_name(action.data.workflow_id, action.data.order_idx, action.data.name)
        job_definition_name = action.data.engine_name
        _logger.info("AWS_Batch: job-name={0}, job_definition_name={1}".format(job_name, job_definition_name))

        try:
            is_continue_on_failure = True if action.data.on_failure == "CONTINUE" else False
            is_last_action = True if action.data.last_in_workflow else False
            workflow_instance_id = action.data.workflow_instance_id
            in_val = [{'name': 'is_continue_on_failure', 'value': str(is_continue_on_failure)},
                      {'name': 'is_last_action', 'value': str(is_last_action)},
                      {'name': 'sns_arn', 'value': str(self.sns_arn)},
                      {'name': 'workflow_instance_id', "value": workflow_instance_id},
                      {'name': 'retries_on_failures', "value": "3"}]

            response = boto3.client('batch').submit_job(jobName=job_name,
                                                        jobDefinition=self._get_latest_active_job_definition(job_definition_name),
                                                        jobQueue=self.batch_queue,
                                                        containerOverrides={
                                                            'environment':
                                                                [{'name': 'DART_ACTION_ID', 'value': action.id},
                                                                 {'name': 'DART_ACTION_USER_ID', 'value': datastore_user_id},
                                                                 {'name': 'input_env', 'value': json.dumps(in_val)}]
                                                        })
        except Exception as err:
            _logger.error('AWS_Batch: failed to run batch job-def-name={0}, reasons: {1}'.format(job_definition_name, err))
            raise err

        _logger.info("AWS_Batch: job_id = {0} for job_name={1}".format(response['jobId'], job_name))
        return response['jobId']

    @staticmethod
    def _batch_job_failed(client, batch_job_id):
        jobs = client.describe_jobs(jobs=[batch_job_id])
        try:
            return jobs['jobs'][0]['status'] == 'FAILED'
        except:
            return False


    def _transition_stale_pending_actions_to_queued(self):
        _logger.info('transitioning stale actions to queued')
        client = boto3.client('batch')
        action_service = self._action_service
        assert isinstance(action_service, ActionService)
        actions = action_service.find_stale_pending_actions()
        for action in actions:
            _logger.error('found stale action with id: %s' % action.id)
            if action.data.batch_job_id and self._batch_job_failed(client, action.data.batch_job_id):
                # If action already has a batch_job_id, it has already tried creating the container on batch and failed.
                action_service.update_action_state(
                    action=action,
                    state=ActionState.FAILED,
                    error_message=action.data.error_message,
                    conditional=lambda a: a.data.state == ActionState.PENDING
                )
                self._trigger_proxy.complete_action(action.id, ActionState.FAILED, action.data.error_message)


    @staticmethod
    def _launch_in_memory_engine(engine, engine_instance, action, datastore_user_id):
        def target():
            engine_instance.run()
        os.environ['DART_ACTION_ID'] = action.id
        os.environ['DART_ACTION_USER_ID'] = datastore_user_id
        p = Process(target=target)
        p.start()
        values = (engine.data.name, p.pid, action.id)
        _logger.info('started in memory engine (name=%s) in process (pid=%s) to run action (id=%s)' % values)


class Counter(object):
    def __init__(self, **thresholds):
        self._thresholds = thresholds
        self._current = {k: 0 for k, v in self._thresholds.iteritems()}

    def increment(self):
        for k in self._current: self._current[k] += 1

    def is_ready(self, key):
        if self._current[key] > self._thresholds[key]:
            self._current[key] = 0
            return True
        return False


if __name__ == '__main__':
    Worker(EngineWorker(), _logger).run()
