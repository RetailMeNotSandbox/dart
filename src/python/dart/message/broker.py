from abc import abstractmethod
import base64
import json
from dart.util.logging_utils import DartLogger
from flask import g
from pydoc import locate
import random
from boto.regioninfo import RegionInfo
from boto.sqs.connection import SQSConnection
from boto.sqs.jsonmessage import JSONMessage
from dart.model.message import MessageState
from dart.service.message import MessageService


_logger = DartLogger(__name__)


class MessageBroker(object):
    @abstractmethod
    def set_app_context(self, app_context):
        """ :type app_context: dart.context.context.AppContext """
        raise NotImplementedError

    @abstractmethod
    def send_message(self, message):
        """
        :param message: the message to send
        :type message: dict
        """
        raise NotImplementedError

    @abstractmethod
    def receive_message(self, handler):
        """
        :param handler: callback function that handles the message
        :type handler: function[str, dict]
        """
        raise NotImplementedError


class SqsJsonMessageBroker(MessageBroker):
    def __init__(self, queue_name, aws_access_key_id=None, aws_secret_access_key=None, region='us-east-1',
                 endpoint=None, is_secure=True, port=None, incoming_message_class='boto.sqs.jsonmessage.JSONMessage'):
        self._region = RegionInfo(name=region, endpoint=endpoint) if region and endpoint else None
        self._queue_name = queue_name
        self._is_secure = is_secure
        self._port = port
        self._incoming_message_class = incoming_message_class
        self._aws_access_key_id = aws_access_key_id
        self._aws_secret_access_key = aws_secret_access_key
        self._message_class = locate(self._incoming_message_class)
        self._queue = None
        self._message_service = None

    def set_app_context(self, app_context):
        self._message_service = app_context.get(MessageService)

    def send_message(self, message):
        _logger.info("sending message: %s" % message)

        # dart always uses the JSONMessage format
        if (message and type(message) is dict and g.request_id is not None):
            message['request_id'] = str(g.request_id)
        self.queue.write(JSONMessage(self.queue, message))

    def receive_message(self, handler, wait_time_seconds=20):
        # randomly purge old messages
        if random.randint(0, 100) < 1:
            self._message_service.purge_old_messages()

        sqs_message = self.queue.read(wait_time_seconds=wait_time_seconds)
        if not sqs_message:
            _logger.debug("Receieving message. no message received.")
            return

        sqs_message_body = self._get_body(sqs_message)
        request_id = ''
        if ((g is not None) and (type(sqs_message_body) is dict) and (sqs_message_body.get('request_id') is not None)):
            # We cannot use g.request_id since for Workers (Trigger, Subscription, Engine do not have an app context)
            request_id = sqs_message_body.get('request_id')

        message = self._message_service.get_message(sqs_message.id, raise_when_missing=False)
        previous_handler_failed = False
        result_state = MessageState.COMPLETED
        if not message:
            _logger.warn("%s Receieving message. The message was not found in message table. Saving sqs_message_body %s" % (request_id, json.dumps(sqs_message_body)))
            message = self._message_service.save_message(sqs_message.id, json.dumps(sqs_message_body), MessageState.RUNNING)

        elif message:

            _logger.info("%s Receieving message: %s" % (request_id, message))
            if message.state in [MessageState.COMPLETED, MessageState.FAILED]:
                _logger.warn('%s bailing on sqs message with id=%s because it was redelivered' % (request_id, sqs_message.id))
                self.queue.delete_message(sqs_message)
                return

            if message.state in [MessageState.RUNNING]:
                # the DB says its running, but is it REALLY running?
                ecs_task_status = self._message_service.get_ecs_task_status(message)
                if ecs_task_status == 'RUNNING':
                    # ok, it was really running.  return and let the visibility timeout resend the message later
                    return
                if not ecs_task_status or ecs_task_status == 'STOPPED':
                    # it seems the container was lost, so mark this message as failed
                    previous_handler_failed = True
                    result_state = MessageState.FAILED

        handler(sqs_message.id, sqs_message_body, previous_handler_failed)
        self._message_service.update_message_state(message, result_state)
        self.queue.delete_message(sqs_message)

    @staticmethod
    def _get_body(message):
        if type(message.get_body()) is dict:
            return message.get_body()
        try:
            # dart's messages are decoded like JSONMessage
            value = base64.b64decode(message.get_body().encode('utf-8')).decode('utf-8')
            value = json.loads(value)
        except:
            # s3 event notifications are raw
            value = json.loads(message.get_body())
        return value

    @property
    def queue(self):
        if self._queue:
            return self._queue
        conn = SQSConnection(self._aws_access_key_id, self._aws_secret_access_key, self._is_secure, self._port, region=self._region)
        self._queue = conn.create_queue(self._queue_name)
        self._queue.set_message_class(self._message_class)
        return self._queue
