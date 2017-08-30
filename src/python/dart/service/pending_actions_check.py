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

    def get_not_completed_workflow_instances(self, workflow_id, workflow_service):
        wf = workflow_service.get_workflow(workflow_id, raise_when_missing=False)
        if not wf:
            _logger.info('Zombie Check: workflow (id={wf_id}) not found. log-info: {log_info}'.
                         format(wf_id=workflow_id, log_info=workflow_msg.get('log_info')))
            return None

        if wf.data.state != WorkflowState.ACTIVE:
            _logger.info('Zombie Check: expected workflow (id={wf_id}) to be in ACTIVE state. log-info: {log_info}'.
                         format(wf_id=workflow_id, log_info=workflow_msg.get('log_info')))

        # get all workflow_instances of current workflow:
        NOT_COMPLETE_STATES = ['QUEUED', 'RUNNING']
        current_wf_instances = workflow_service.find_workflow_instances(workflow_id, NOT_COMPLETE_STATES)
        _logger.info('Zombie Check: Found workflow instance ids (workflow_id={0}) instances = {1}'.format(workflow_id, current_wf_instances))

        return current_wf_instances

    def get_instance_actions(self, current_wf_instances):
        # get all actions of not completed workflow_instances
        incomplete_actions = []
        action_2_wf_instance = {}
        for wf_instance in current_wf_instances:
            wf_instance_actions = self._action_service.find_actions(workflow_instance_id=wf_instance.id)
            incomplete_actions.extend(wf_instance_actions)
            for action in wf_instance_actions:
                action_2_wf_instance[action.id] = wf_instance

        jobs_2_actions = {}
        for action in incomplete_actions:
            if action.data.batch_job_id:
                jobs_2_actions[action.data.batch_job_id] = action

        return incomplete_actions, jobs_2_actions, action_2_wf_instance

    def handle_done_batch_jobs_with_not_complete_wf_instances(self, batch_jobs, jobs_2_actions, action_2_wf_instance, workflow_service):
        for job in batch_jobs.get('jobs', []):
            # jobs fail + action not-failed => fail workflow instance and action
            action = jobs_2_actions[job.get('jobId')]
            if action:
                wf_instance = action_2_wf_instance[action.id]
                if job.get('status') == 'FAILED' and not (action.data.state  in ['FAILED', 'COMPLETED']):
                    _logger.info("Zombie Check: Job {0} is failed but action {0} is not failed/completed. Updating action and workflow_instance to FAILED".format(job.get('jobId'), action.id))
                    self._action_service.update_action_state(action, ActionState.FAILED, action.data.error_message)
                    workflow_service.update_workflow_instance_state(wf_instance, WorkflowInstanceState.FAILED)

                # Jobs complete + action not-failed => mark workflow instance as complete and mark actions as complete
                if job.get('status') == 'COMPLETED' and not (action.data.state in ['FAILED', 'COMPLETED']):
                    _logger.info("Zombie Check: Job {0} is completed but action {0} is not failed/completed. Updating action to COMPLETED".format(job.get("jobId"), action.id))
                    self._action_service.update_action_state(action, ActionState.COMPLETED, action.data.error_message)
                    workflow_service.update_workflow_instance_state(wf_instance, WorkflowInstanceState.FAILED)

    def find_pending_dart_actions(self, workflow_id, workflow_service):
        ''' We send workflow_service to avoid cyclical injection from workflow_service '''
        current_wf_instances = self.get_not_completed_workflow_instances(workflow_id, workflow_service)
        if current_wf_instances:
            incomplete_actions, jobs_2_actions, action_2_wf_instance = self.get_instance_actions(current_wf_instances)
            batch_job_ids = [job.data.batch_job_id for job in incomplete_actions]
            _logger.info("Zombie Check: extract job_ids {0} form incomplete actions {1}".format(batch_job_ids, [act.id for act in incomplete_actions]))

            try:
                batch_jobs = self._batch_client.describe_jobs(jobs=batch_job_ids)
            except Exception as err:
                _logger.error("Zombie Check: failed to execute batch's describe_jobs. err = {0}".format(err))
            else:
                self.handle_done_batch_jobs_with_not_complete_wf_instances(batch_jobs, jobs_2_actions, action_2_wf_instance, workflow_service)

