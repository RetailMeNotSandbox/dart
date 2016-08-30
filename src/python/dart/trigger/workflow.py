from dart.util.logging_utils import DartLogger

from dart.context.locator import injectable
from dart.model.trigger import TriggerType
from dart.trigger.base import TriggerProcessor, execute_trigger

_logger = DartLogger(__name__)


workflow_completion_trigger = TriggerType(
    name='workflow_completion',
    description='Triggering that occurs on the completion of a specific workflow',
    params_json_schema={
        'type': 'object',
        'properties': {
            'completed_workflow_id': {
                'type': 'string',
                'description': 'Trigger fires whenever this workflow completes successfully'
            },
        },
        'additionalProperties': False,
        'required': ['completed_workflow_id'],
    }
)


@injectable
class WorkflowCompletionTriggerProcessor(TriggerProcessor):
    def __init__(self, trigger_proxy, workflow_service):
        self._trigger_proxy = trigger_proxy
        self._workflow_service = workflow_service
        self._trigger_type = workflow_completion_trigger

    def trigger_type(self):
        return self._trigger_type

    def initialize_trigger(self, trigger, trigger_service):
        pass

    def update_trigger(self, unmodified_trigger, modified_trigger):
        return modified_trigger

    def evaluate_message(self, message, trigger_service):
        """ :type message: dict
            :type trigger_service: dart.service.trigger.TriggerService """

        executed_trigger_ids = []
        arg = {'completed_workflow_id': message['workflow_id']}
        for trigger in trigger_service.find_triggers(self._trigger_type.name, arg):
            execute_trigger(trigger, self._trigger_type, self._workflow_service, _logger)
            executed_trigger_ids.append(trigger.id)

        return executed_trigger_ids

    def teardown_trigger(self, trigger, trigger_service):
        pass

    def send_evaluation_message(self, workflow_id):
        self._trigger_proxy.trigger_workflow_completion(workflow_id)
