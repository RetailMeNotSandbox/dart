from dart.util.logging_utils import DartLogger
import math

from dart.context.locator import injectable
from dart.model.trigger import TriggerType, TriggerState
from dart.trigger.base import TriggerProcessor, execute_trigger

_logger = DartLogger(__name__)


subscription_batch_trigger = TriggerType(
    name='subscription_batch',
    description='Triggering that occurs each time subscription has reached the desired amount of unconsumed data',
    params_json_schema={
        'type': 'object',
        'properties': {
            'subscription_id': {'type': 'string', 'description': 'The id of the subscription'},
            'unconsumed_data_size_in_bytes': {
                'type': 'integer',
                'minimum': 1,
                'description': 'The trigger will fire once the unconsumed data size reaches this number of bytes'
            },
        },
        'additionalProperties': False,
        'required': ['subscription_id', 'unconsumed_data_size_in_bytes'],
    }
)


@injectable
class SubscriptionBatchTriggerProcessor(TriggerProcessor):
    def __init__(self, trigger_proxy, subscription_service, subscription_element_service, workflow_service):
        self._trigger_proxy = trigger_proxy
        self._subscription_service = subscription_service
        self._subscription_element_service = subscription_element_service
        self._workflow_service = workflow_service
        self._trigger_type = subscription_batch_trigger

    def trigger_type(self):
        return self._trigger_type

    def initialize_trigger(self, trigger, trigger_service):
        self.send_evaluation_message(trigger.id)

    def update_trigger(self, unmodified_trigger, modified_trigger):
        return modified_trigger

    def evaluate_message(self, message, trigger_service):
        """ :type message: dict
            :type trigger_service: dart.service.trigger.TriggerService """
        trigger_id = message['trigger_id']
        trigger = trigger_service.get_trigger(trigger_id, raise_when_missing=False)
        if not trigger:
            _logger.info('trigger (id=%s) not found' % trigger_id)
            return []
        if trigger.data.state != TriggerState.ACTIVE:
            _logger.info('expected trigger (id=%s) to be in ACTIVE state' % trigger.id)
            return []

        unconsumed_data_size_in_bytes = long(trigger.data.args['unconsumed_data_size_in_bytes'])
        sid = trigger.data.args['subscription_id']
        file_size_sum, file_size_avg =\
            self._subscription_element_service.get_subscription_element_file_size_sum_and_avg(sid)

        if file_size_sum < unconsumed_data_size_in_bytes:
            return []

        # average = sum / count,  count = sum / avg,  adding 10% will help reduce more trips to the db
        predict_limit = lambda fs_sum: int(math.ceil(float(fs_sum / file_size_avg) * 1.1))
        element_ids = []
        s3_path = None
        current_unconsumed_bytes = 0
        while current_unconsumed_bytes < unconsumed_data_size_in_bytes:
            limit = predict_limit(unconsumed_data_size_in_bytes - current_unconsumed_bytes)
            elements = self._subscription_element_service.find_subscription_elements(
                sid, gt_s3_path=s3_path, limit=limit
            )
            for element in elements:
                element_ids.append(element.id)
                current_unconsumed_bytes += element.file_size
                s3_path = element.s3_path
                if current_unconsumed_bytes >= unconsumed_data_size_in_bytes:
                    break

        self._subscription_element_service.reserve_subscription_elements(element_ids)

        execute_trigger(trigger, self._trigger_type, self._workflow_service, _logger)

        return [trigger_id]

    def teardown_trigger(self, trigger, trigger_service):
        pass

    def send_evaluation_message(self, trigger_id):
        self._trigger_proxy.trigger_subscription_evaluation(trigger_id)
