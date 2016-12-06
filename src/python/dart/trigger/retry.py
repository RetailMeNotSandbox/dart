from dart.context.locator import injectable
from dart.model.trigger import TriggerType
from dart.trigger.base import TriggerProcessor

retry_trigger = TriggerType(
    name='retry',
    description='Triggering a workflow to rerun after failure'
)


@injectable
class RetryTriggerProcessor(TriggerProcessor):
    def __init__(self, trigger_proxy, workflow_service):
        self._trigger_proxy = trigger_proxy
        self._workflow_service = workflow_service
        self._trigger_type = retry_trigger

    def trigger_type(self):
        return self._trigger_type

    def initialize_trigger(self, trigger, trigger_service):
        # retry triggers should never be saved, thus never initialized
        pass

    def update_trigger(self, unmodified_trigger, modified_trigger):
        return modified_trigger

    def evaluate_message(self, message, trigger_service):
        """ :type message: dict
            :type trigger_service: dart.service.trigger.TriggerService """
        # always trigger a retry message
        self._workflow_service.run_triggered_workflow(message['workflow_id'], self._trigger_type, retry_num=message['retry_num'])

        # return an empty list since this is not associated with a particular trigger instance
        return []

    def teardown_trigger(self, trigger, trigger_service):
        pass
