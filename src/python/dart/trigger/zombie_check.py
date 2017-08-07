from dart.context.locator import injectable
from dart.model.trigger import TriggerType
from dart.trigger.base import TriggerProcessor
from dart.model.workflow import WorkflowState, WorkflowInstanceState
from dart.model.action import ActionState

import logging
import boto3

_logger = logging.getLogger(__name__)

zombie_check_trigger = TriggerType(
    name='zombie_check',
    description='Check if the actions of current workflow instances are not in (FAILED, SUCCESS) states in Batch'
)

@injectable
class ZombieCheckTriggerProcessor(TriggerProcessor):
    def __init__(self, trigger_proxy, action_service, workflow_service, pending_actions_check):
        self._trigger_proxy = trigger_proxy
        self._action_service = action_service
        self._workflow_service = workflow_service
        self._trigger_type = zombie_check_trigger
        self._pending_actions_check = pending_actions_check
        self._batch_client = boto3.client('batch')

    def trigger_type(self):
        return self._trigger_type

    def initialize_trigger(self, trigger, trigger_service):
        # manual triggers should never be saved, thus never initialized
        pass

    def update_trigger(self, unmodified_trigger, modified_trigger):
        return modified_trigger

    def evaluate_message(self, workflow_msg, trigger_service):
        """ :type message: dict
            :type trigger_service: dart.service.trigger.TriggerService """

        workflow_id = workflow_msg.get('workflow_id')
        self._pending_actions_check.find_pending_dart_actions(workflow_id, self._workflow_service)

        # return an empty list since this is not associated with a particular trigger instance
        return []

    def teardown_trigger(self, trigger, trigger_service):
        pass

    def send_evaluation_message(self, workflow_msg):
        self._trigger_proxy.process_trigger(self._trigger_type, workflow_msg)


