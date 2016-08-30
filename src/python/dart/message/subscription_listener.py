import json
from dart.util.logging_utils import DartLogger
import traceback
import urllib

from dart.context.locator import injectable
from dart.message.call import SubscriptionCall
from dart.model.subscription import SubscriptionState


_logger = DartLogger(__name__)


@injectable
class SubscriptionListener(object):
    def __init__(self, subscription_broker, subscription_service, subscription_element_service, trigger_service,
                 subscription_batch_trigger_processor, emailer):
        self._subscription_broker = subscription_broker
        self._subscription_service = subscription_service
        self._subscription_element_service = subscription_element_service
        self._trigger_service = trigger_service
        self._subscription_batch_trigger_processor = subscription_batch_trigger_processor
        self._emailer = emailer
        self._handlers = {
            SubscriptionCall.GENERATE: self._handle_create_subscription_call
        }

    def await_call(self, wait_time_seconds=20):
        self._subscription_broker.receive_message(self._handle_call, wait_time_seconds)

    def _handle_call(self, message_id, message, previous_handler_failed):
        if 'Subject' in message and message['Subject'] == 'Amazon S3 Notification':
            handler = self._handle_s3_event
        else:
            call = message['call']
            if call not in self._handlers:
                raise Exception('no handler defined for call: %s' % call)
            handler = self._handlers[call]
        try:
            handler(message_id, message, previous_handler_failed)
        except Exception:
            _logger.error(json.dumps(traceback.format_exc()))

    # message_id and previous_handler_failed are unused because the conditional insert makes this funciton idempotent
    # noinspection PyUnusedLocal
    def _handle_s3_event(self, message_id, message, previous_handler_failed):
        """ :type message: dict """

        # Helpful data to help understand this function:
        #
        #     - http://docs.aws.amazon.com/AmazonS3/latest/dev/notification-content-structure.html
        #     - dart/tools/sample-s3event_sqs-message.json
        #
        for record in json.loads(message['Message'])['Records']:
            if not record['eventName'].startswith('ObjectCreated:'):
                continue
            s3_path = 's3://' + record['s3']['bucket']['name'] + '/' + urllib.unquote(record['s3']['object']['key'])
            size = record['s3']['object']['size']
            for subscription in self._subscription_service.find_matching_subscriptions(s3_path):
                success = self._subscription_element_service.conditional_insert_subscription_element(
                    subscription, s3_path, size
                )
                if success:
                    self._trigger_service.evaluate_subscription_triggers(subscription)

    def _handle_create_subscription_call(self, message_id, message, previous_handler_failed):
        subscription = self._subscription_service.get_subscription(message['subscription_id'])
        subscription = self._subscription_service.update_subscription_message_id(subscription, message_id)

        if previous_handler_failed:
            self._subscription_service.update_subscription_state(subscription, SubscriptionState.FAILED)
            self._emailer.send_subscription_failed_email(subscription)
            return

        self._subscription_element_service.generate_subscription_elements(subscription)
        self._trigger_service.evaluate_subscription_triggers(subscription)
        self._emailer.send_subscription_completed_email(subscription)
