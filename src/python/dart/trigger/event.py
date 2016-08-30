from dart.util.logging_utils import DartLogger

from dart.context.locator import injectable
from dart.model.event import EventState
from dart.model.trigger import TriggerType
from dart.trigger.base import TriggerProcessor, execute_trigger

_logger = DartLogger(__name__)


event_trigger = TriggerType(
    name='event',
    description='Triggering from a registered event',
    params_json_schema={
        'type': 'object',
        'properties': {
            'event_id': {'type': 'string', 'description': 'The id for the registered event'},
        },
        'additionalProperties': False,
        'required': ['event_id'],
    }
)


@injectable
class EventTriggerProcessor(TriggerProcessor):
    def __init__(self, workflow_service, event_service):
        self._workflow_service = workflow_service
        self._event_service = event_service
        self._trigger_type = event_trigger

    def trigger_type(self):
        return self._trigger_type

    def initialize_trigger(self, trigger, trigger_service):
        pass

    def update_trigger(self, unmodified_trigger, modified_trigger):
        return modified_trigger

    def evaluate_message(self, message, trigger_service):
        """ :type message: dict
            :type trigger_service: dart.service.trigger.TriggerService """
        event_id = message['event_id']
        event = self._event_service.get_event(event_id, raise_when_missing=False)
        if not event:
            _logger.warn('Event not found (id=%s)' % event_id)
            return []
        if event.data.state == EventState.INACTIVE:
            _logger.warn('Event INACTIVE (id=%s)' % event.id)
            return []

        executed_trigger_ids = []
        arg = {'event_id': event_id}
        for trigger in trigger_service.find_triggers(self._trigger_type.name, arg):
            execute_trigger(trigger, self._trigger_type, self._workflow_service, _logger)
            executed_trigger_ids.append(trigger.id)

        return executed_trigger_ids

    def teardown_trigger(self, trigger, trigger_service):
        pass
