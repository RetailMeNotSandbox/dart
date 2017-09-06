from dart.context.locator import injectable
from dart.model.workflow import WorkflowState, WorkflowInstanceState
from dart.model.action import ActionState

import logging
import boto3

_logger = logging.getLogger(__name__)

@injectable
class PendingActionsCheck(object):
    def __init__(self, action_service):
        self._action_service = action_service
        self._batch_client = boto3.client('batch')

    def get_queued_or_running_workflow_instances(self, workflow_id, workflow_service):
        wf = workflow_service.get_workflow(workflow_id, raise_when_missing=False)
        if not wf:
            _logger.info('Zombie Check: workflow (id={wf_id}) not found.'.format(wf_id=workflow_id))
            return []

        if wf.data.state != WorkflowState.ACTIVE:
            _logger.info('Zombie Check: expected workflow (id={wf_id}) to be in ACTIVE state'.format(wf_id=workflow_id))

        # get all workflow_instances of current workflow:
        INCOMPLETE_STATES = ['QUEUED', 'RUNNING']
        queued_or_running_wf_instances = workflow_service.find_workflow_instances(workflow_id, states=INCOMPLETE_STATES)
        _logger.info('Zombie Check: Found workflow instance ids (workflow_id={0}) instances = {1}'.format(workflow_id, queued_or_running_wf_instances))

        return queued_or_running_wf_instances

    def get_instance_actions(self, queued_or_running_wf_instances):
        # get all actions of not completed workflow_instances
        incomplete_actions = []  # action that belong to a running or queued workflow, not related to the action's state
        action_2_wf_instance = {}  # mapping an action to its workflow instance
        for wf_instance in queued_or_running_wf_instances:
            wf_instance_actions = self._action_service.find_actions(workflow_instance_id=wf_instance.id)
            incomplete_actions.extend(wf_instance_actions)
            for action in wf_instance_actions:
                action_2_wf_instance[action.id] = wf_instance

        # reverse lookup the actions from their job_id
        jobs_2_actions = {}
        actions_without_jobs = []
        for action in incomplete_actions:
            if action.data.batch_job_id:
                jobs_2_actions[action.data.batch_job_id] = action
            else:
                actions_without_jobs.append(action)

        return incomplete_actions, jobs_2_actions, action_2_wf_instance, actions_without_jobs

    def update_action_and_wf_instance_states(self, action, action_state, wf_instance, wf_instance_state, workflow_service):
        self._action_service.update_action_state(action, action_state, action.data.error_message)
        workflow_service.update_workflow_instance_state(wf_instance, wf_instance_state)

    def handle_done_batch_jobs_with_not_complete_wf_instances(self, batch_jobs, jobs_2_actions, action_2_wf_instance, workflow_service):
        ''' The batch job is in SUCCEEDED/FAILED state but the action is not '''
        for job in batch_jobs.get('jobs', []):
            # jobs fail + action not-failed => fail workflow instance and action
            action = jobs_2_actions[job.get('jobId')]
            if action:
                wf_instance = action_2_wf_instance[action.id]
                if job.get('status') == 'FAILED' and not (action.data.state in ['FAILED', 'COMPLETED']):
                    _logger.info("Zombie Check: Job {0} is failed but action {0} is not failed/completed. Updating action and workflow_instance to FAILED".format(job.get('jobId'), action.id))
                    self.update_action_and_wf_instance_states(action=action,
                                                              action_state=ActionState.FAILED,
                                                              wf_instance=wf_instance,
                                                              wf_instance_state=WorkflowInstanceState.FAILED,
                                                              workflow_service=workflow_service)

                # Jobs complete + action not-failed => mark workflow instance as complete and mark actions as complete
                if job.get('status') == 'COMPLETED' and not (action.data.state in ['FAILED', 'COMPLETED']):
                    _logger.info("Zombie Check: Job {0} is completed but action {0} is not failed/completed. Updating action to COMPLETED".format(job.get("jobId"), action.id))
                    self.update_action_and_wf_instance_states(action=action,
                                                              action_state=ActionState.COMPLETED,
                                                              wf_instance=wf_instance,
                                                              wf_instance_state=WorkflowInstanceState.FAILED,
                                                              workflow_service=workflow_service)

    def handle_actions_without_batch_job_ids(self, actions_without_jobs, action_2_wf_instance, workflow_service):
        ''' Fail actions and their workflow instances that do not have a batch job_ida '''
        for jobless_action in actions_without_jobs:
            jobless_wf_instance = action_2_wf_instance[jobless_action.id]
            jobless_wf_instance_id = jobless_wf_instance.id if jobless_wf_instance else None
            _logger.error("Zombie Check: action {0} has no batch_job_id. Failing the action and its workflow instance {1}.".format(jobless_action, jobless_wf_instance_id))
            self.update_action_and_wf_instance_states(action=jobless_action,
                                                      action_state=ActionState.FAILED,
                                                      wf_instance=jobless_wf_instance,
                                                      wf_instance_state=WorkflowInstanceState.FAILED,
                                                      workflow_service=workflow_service)

    def handle_actions_with_deleted_batch_jobs(self, all_batch_job_ids, existing_job_ids, jobs_2_actions, action_2_wf_instance, workflow_service):
        ''' Find actions whose batch_job info is deleted from Batch history (24 hours retention for jobs in SUCCEEDED/FAILED state) '''
        def diff(first, second):
            second = set(second)
            return [item for item in first if item not in second]

        deleted_job_ids = diff(all_batch_job_ids, existing_job_ids)
        for deleted_job_id in deleted_job_ids:
            action = jobs_2_actions.get(deleted_job_id)
            action_id = action.id if action else None
            if action:
                wf_instance = action_2_wf_instance.get(action_id)
                wf_instance_id = wf_instance.id if wf_instance else []
                if wf_instance:
                    self.update_action_and_wf_instance_states(action=action,
                                                              action_state=ActionState.FAILED,
                                                              wf_instance=wf_instance,
                                                              wf_instance_state=WorkflowInstanceState.FAILED,
                                                              workflow_service=workflow_service)
            _logger.info("Zombie Check: Job {0} info is deleted from Batch, Failing action {1} + workflow instance {2}".format(deleted_job_id, action_id, wf_instance_id))


    def find_pending_dart_actions(self, workflow_id, workflow_service):
        ''' We send workflow_service to avoid cyclical injection from workflow_service '''

        try:
            _logger.info('Zombie Check: Looking for pending action for workflow {wf_id}.'.format(wf_id=workflow_id))
            queued_or_running_wf_instances = self.get_queued_or_running_workflow_instances(workflow_id, workflow_service)
            if queued_or_running_wf_instances:
                incomplete_actions, jobs_2_actions, action_2_wf_instance, actions_without_jobs = self.get_instance_actions(queued_or_running_wf_instances)

                batch_job_ids = jobs_2_actions.keys()
                _logger.info("Zombie Check: extract job_ids {0} form incomplete actions {1}".format(batch_job_ids, [act.id for act in incomplete_actions]))

                if batch_job_ids:
                    try:
                        # there should not be too many jobs per wf_instance so we do not need to retry getting more batches.
                        batch_jobs = self._batch_client.describe_jobs(jobs=batch_job_ids)
                        existing_job_ids = filter(None, [job.get('jobId') for job in batch_jobs.get('jobs', [])])
                    except Exception as err:
                        _logger.error("Zombie Check: failed to execute batch's describe_jobs. err = {0}".format(err))
                    else:
                        self.handle_done_batch_jobs_with_not_complete_wf_instances(batch_jobs,
                                                                                   jobs_2_actions,
                                                                                   action_2_wf_instance,
                                                                                   workflow_service)

                        self.handle_actions_without_batch_job_ids(actions_without_jobs=actions_without_jobs,
                                                                  action_2_wf_instance=action_2_wf_instance,
                                                                  workflow_service=workflow_service)

                        self.handle_actions_with_deleted_batch_jobs(all_batch_job_ids=batch_job_ids,
                                                                    existing_job_ids=existing_job_ids,
                                                                    jobs_2_actions=jobs_2_actions,
                                                                    action_2_wf_instance=action_2_wf_instance,
                                                                    workflow_service=workflow_service)
                else:
                    self.handle_actions_without_batch_job_ids(actions_without_jobs=actions_without_jobs,
                                                              action_2_wf_instance=action_2_wf_instance,
                                                              workflow_service=workflow_service)

        except Exception as err:
            _logger.error("Zombie Check: failed to find pending dart actions for workflow {0}. err={1}".format(workflow_id, err))






