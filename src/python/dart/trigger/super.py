import copy
from datetime import datetime
from dart.util.logging_utils import DartLogger

from dart.context.locator import injectable
from dart.model.trigger import TriggerType, Trigger
from dart.trigger.base import TriggerProcessor, execute_trigger

_logger = DartLogger(__name__)


super_trigger = TriggerType(
    name='super',
    description='Triggering that occurs whenever all or any specified triggers have fired',
    params_json_schema={
        'type': 'object',
        'properties': {
            'fire_after': {
                'type': 'string',
                'enum': ['ALL', 'ANY'],
                'default': 'ALL',
                'description': 'Fire this trigger after ALL or ANY of the specified triggers have fired',
            },
            'completed_trigger_ids': {
                'x-schema-form': {'type': 'tabarray', 'title': "{{ value || 'trigger_id ' + $index }}"},
                'type': 'array',
                'items': {'type': 'string'},
                'minItems': 1,
            },
        },
        'additionalProperties': False,
        'required': ['fire_after', 'completed_trigger_ids'],
    }
)


@injectable
class SuperTriggerProcessor(TriggerProcessor):
    def __init__(self, workflow_service):
        self._workflow_service = workflow_service
        self._trigger_type = super_trigger

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
        completed_trigger_id = message['trigger_id']
        arg = {'completed_trigger_ids': [completed_trigger_id]}
        for s_trigger in trigger_service.find_triggers(self._trigger_type.name, arg):
            assert isinstance(s_trigger, Trigger)

            operator = s_trigger.data.args['fire_after']
            if operator == 'ANY':
                self._fire_trigger(executed_trigger_ids, s_trigger)
                continue

            assert operator == 'ALL', 'unexpected super trigger operator: %s' % operator

            extra_data = copy.deepcopy(s_trigger.data.extra_data or {})
            if 'completed_trigger_id_times' not in extra_data:
                extra_data['completed_trigger_id_times'] = {}
            extra_data['completed_trigger_id_times'][completed_trigger_id] = datetime.utcnow().isoformat()

            completed_trigger_ids = set(extra_data['completed_trigger_id_times'].keys())
            all_completed = True
            for ctid in s_trigger.data.args['completed_trigger_ids']:
                if ctid not in completed_trigger_ids:
                    all_completed = False
                    break

            if not all_completed:
                trigger_service.update_trigger_extra_data(s_trigger, extra_data)
                continue

            extra_data['completed_trigger_id_times'] = {}
            trigger_service.update_trigger_extra_data(s_trigger, extra_data)

            self._fire_trigger(executed_trigger_ids, s_trigger)

        return executed_trigger_ids

    def _fire_trigger(self, executed_trigger_ids, s_trigger):
        execute_trigger(s_trigger, self._trigger_type, self._workflow_service, _logger)
        executed_trigger_ids.append(s_trigger.id)

    def teardown_trigger(self, trigger, trigger_service):
        pass
