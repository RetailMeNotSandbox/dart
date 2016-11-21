from dart.context.locator import injectable
from dart.model.trigger import TriggerType
from dart.trigger.base import TriggerProcessor


manual_trigger = TriggerType(
    name='manual',
    description='Manual triggering by a user'
)


@injectable
class ManualTriggerProcessor(TriggerProcessor):
    def __init__(self, trigger_proxy, workflow_service):
        self._trigger_proxy = trigger_proxy
        self._workflow_service = workflow_service
        self._trigger_type = manual_trigger

    def trigger_type(self):
        return self._trigger_type

    def initialize_trigger(self, trigger, trigger_service):
        # manual triggers should never be saved, thus never initialized
        pass

    def update_trigger(self, unmodified_trigger, modified_trigger):
        return modified_trigger

    def evaluate_message(self, message, trigger_service):
        """ :type message: dict
            :type trigger_service: dart.service.trigger.TriggerService """
        # always trigger a manual message
        self._workflow_service.run_triggered_workflow(message, self._trigger_type)

        # return an empty list since this is not associated with a particular trigger instance
        return []

    def teardown_trigger(self, trigger, trigger_service):
        pass

    def send_evaluation_message(self, workflow_json):
        self._trigger_proxy.process_trigger(self._trigger_type, workflow_json)
