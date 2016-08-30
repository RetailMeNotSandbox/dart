import json
from dart.util.logging_utils import DartLogger
import logging.config
import os
from pydoc import locate
import time
from datetime import datetime
from itertools import islice
from multiprocessing import Process

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

_logger = DartLogger(__name__)


class EngineWorker(Tool):
    def __init__(self):
        super(EngineWorker, self).__init__(_logger)
        self._engine_taskrunner_ecs_cluster = self.dart_config['dart'].get('engine_taskrunner_ecs_cluster')
        self._engine_service = self.app_context.get(EngineService)
        self._action_service = self.app_context.get(ActionService)
        self._datastore_service = self.app_context.get(DatastoreService)
        self._trigger_proxy = self.app_context.get(TriggerProxy)
        self._sleep_seconds = 0.7
        self._counter = Counter(transition_queued=1, transition_stale=1, transition_orphaned=60, scale_down=120)

    def run(self):
        time.sleep(self._sleep_seconds)
        self._counter.increment()

        if self._counter.is_ready('transition_queued'):
            self._transition_queued_actions_to_pending()

        if self._counter.is_ready('transition_stale'):
            self._transition_stale_pending_actions_to_queued()

        if self._counter.is_ready('transition_orphaned'):
            self._transition_orphaned_actions_to_failed()

        if self._counter.is_ready('scale_down') and self._engine_taskrunner_ecs_cluster:
            self._scale_down_unused_ecs_container_instances()

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

                if self.dart_config['dart'].get('use_local_engines'):
                    config = self.dart_config['engines'][engine.data.name]
                    engine_instance = locate(config['path'])(**config.get('options', {}))
                    self._launch_in_memory_engine(engine, engine_instance, action)
                    # empty string allows differentiation from null, yet is still falsey
                    action_service.update_action_ecs_task_arn(action, '')

                elif engine.data.ecs_task_definition_arn:
                    ecs_task_arn = self._try_run_task(engine, action)
                    if ecs_task_arn:
                        action_service.update_action_ecs_task_arn(action, ecs_task_arn)
                    else:
                        # no task arn means there isn't enough capacity at the moment, so try again later
                        action_service.update_action_state(action, ActionState.QUEUED, action.data.error_message)

                else:
                    msg = 'engine %s has no ecs_task_definition and local engines are not allowed'
                    raise Exception(msg % engine.data.name)

            except DartConditionalUpdateFailedException:
                # another engine worker picked it up
                continue

            except Exception as e:
                _logger.error('error transitioning action (id=%s) to PENDING: %s' % (action.id, e.message))

            finally:
                db.session.rollback()

    @db_mutex(Mutexes.START_ENGINE_TASK)
    def _try_run_task(self, engine, action):
        _logger.info('trying to run ecs task')

        response = boto3.client('ecs').run_task(
            cluster=self._engine_taskrunner_ecs_cluster,
            taskDefinition=engine.data.ecs_task_definition_arn,
            overrides={
                'containerOverrides': [
                    {
                        'name': containerDefinition['name'],
                        'environment': [{'name': 'DART_ACTION_ID', 'value': action.id}]
                    }
                    for containerDefinition in engine.data.ecs_task_definition['containerDefinitions']
                ]
            },
            count=1,
            startedBy='dart-engine-worker'
        )
        if len(response['failures']) > 0:
            for failure in response['failures']:
                if failure['reason'].startswith('RESOURCE'):
                    return None
            raise Exception('failed to run ecs task, reasons: %s' % json.dumps(response['failures']))
        return response['tasks'][0]['taskArn']

    def _transition_stale_pending_actions_to_queued(self):
        _logger.info('transitioning stale actions to queued')

        action_service = self._action_service
        assert isinstance(action_service, ActionService)
        actions = action_service.find_stale_pending_actions()
        for action in actions:
            _logger.error('found stale action with id: %s' % action.id)
            action_service.update_action_state(
                action=action,
                state=ActionState.QUEUED,
                error_message=action.data.error_message,
                conditional=lambda a: a.data.state == ActionState.PENDING
            )

    def _transition_orphaned_actions_to_failed(self):
        _logger.info('transitioning orphaned actions to failed')

        action_service = self._action_service
        assert isinstance(action_service, ActionService)
        actions = action_service.find_actions(states=[ActionState.PENDING, ActionState.RUNNING])
        actions_by_ecs_task_arn = {a.data.ecs_task_arn: a for a in actions if a.data.ecs_task_arn}

        batch_size = 50
        task_arns = iter(actions_by_ecs_task_arn.keys())
        while True:
            task_arn_batch = list(islice(task_arns, batch_size))
            if not task_arn_batch:
                break
            response = boto3.client('ecs').describe_tasks(
                cluster=self._engine_taskrunner_ecs_cluster,
                tasks=task_arn_batch
            )
            for task in response['tasks']:
                if task['desiredStatus'] == 'STOPPED':
                    action = actions_by_ecs_task_arn[task['taskArn']]
                    error_message = 'the ECS task STOPPED unexpectedly'
                    self._trigger_proxy.complete_action(action.id, ActionState.FAILED, error_message)

    @db_mutex(Mutexes.START_ENGINE_TASK)
    def _scale_down_unused_ecs_container_instances(self):
        _logger.info('checking for ecs container instances that are ready to scale down')

        # first get a list of all the ecs container instance ids in the engine taskrunner cluster
        container_instance_arns = []
        paginator = boto3.client('ecs').get_paginator('list_container_instances')
        for response in paginator.paginate(cluster=self._engine_taskrunner_ecs_cluster):
            container_instance_arns.extend(response.get('containerInstanceArns'))

        # next, filter to just the ones that are active but have no activity
        batch_size = 50
        container_instance_arns_by_ec2_instance_id = {}
        container_instance_arns_iter = iter(container_instance_arns)
        while True:
            container_instance_arn_batch = list(islice(container_instance_arns_iter, batch_size))
            if not container_instance_arn_batch:
                break
            response = boto3.client('ecs').describe_container_instances(
                cluster=self._engine_taskrunner_ecs_cluster,
                containerInstances=container_instance_arn_batch
            )
            for instance in response.get('containerInstances'):
                if instance.get('status') == 'ACTIVE' \
                        and instance.get('runningTasksCount') == 0 \
                        and instance.get('pendingTasksCount') == 0:
                    instance_id = instance.get('ec2InstanceId')
                    container_instance_arn = instance.get('containerInstanceArn')
                    container_instance_arns_by_ec2_instance_id[instance_id] = container_instance_arn

        # don't try to scale down if we only have 1 instance (the ASG min)
        if len(container_instance_arns_by_ec2_instance_id.keys()) == 1:
            return

        # lastly, terminate the first one we see that is within 5 minutes of crossing the hour boundary
        threshold_in_seconds = 300
        seconds_per_hour = 3600
        paginator = boto3.client('ec2').get_paginator('describe_instances')
        instance_id_iter = iter(container_instance_arns_by_ec2_instance_id.keys())
        while True:
            instance_id_batch = list(islice(instance_id_iter, batch_size))
            if not instance_id_batch:
                break
            for response in paginator.paginate(InstanceIds=instance_id_batch):
                for reservation in response.get('Reservations'):
                    for instance in reservation.get('Instances'):
                        launch_time = instance.get('LaunchTime')
                        utcnow = datetime.utcnow().replace(tzinfo=tzutc())
                        time_running = utcnow - launch_time
                        hours_running = time_running.seconds / seconds_per_hour
                        threshold_hours_running = (time_running.seconds + threshold_in_seconds) / seconds_per_hour

                        if hours_running != threshold_hours_running:
                            instance_id = instance.get('InstanceId')
                            boto3.client('ecs').deregister_container_instance(
                                cluster=self._engine_taskrunner_ecs_cluster,
                                containerInstance=container_instance_arns_by_ec2_instance_id[instance_id],
                                force=False
                            )
                            boto3.client('autoscaling').terminate_instance_in_auto_scaling_group(
                                InstanceId=instance_id,
                                ShouldDecrementDesiredCapacity=True
                            )
                            break

    @staticmethod
    def _launch_in_memory_engine(engine, engine_instance, action):
        def target():
            engine_instance.run()
        os.environ['DART_ACTION_ID'] = action.id
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
