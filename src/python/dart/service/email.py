import logging
import urllib
from textwrap import dedent
from mailer import Mailer, Message
from retrying import retry
from dart.context.locator import injectable
from dart.util.config import _get_dart_host

from Queue import Queue
from threading import Thread


_logger = logging.getLogger(__name__)


@injectable
class Emailer(object):
    def __init__(self, dart_config):
        email_config = dart_config['email']
        self._env_name = dart_config['dart']['env_name'].upper()
        self._mailer = Mailer(**email_config['mailer'])
        self._from = email_config['from']
        self._cc_on_error = email_config['cc_on_error']
        self._debug = email_config.get('debug', False)
        self._suppress_send = email_config.get('suppress_send', False)
        self._dart_host = _get_dart_host(dart_config)

        # We have one mailer being used in trigger_listener
        self._email_queue = Queue(maxsize=1000) # we should not have that many emails pending to be sent
        email_worker = Thread(target=self.send_queued_email_runner, args=(self._email_queue,))
        email_worker.setDaemon(True)  # we run in a container, when it exits this thread will exit too.
        email_worker.start()


    def get_entity_link(self, entity, action_id):
        origin_param = '["id=%s"]' %(action_id)
        converted_param = urllib.quote(origin_param, safe='')
        path = 'https://%s/#/entities/%s?f=' % (self._dart_host, entity)
        return path + converted_param


    def get_workflow_manager_link(self, workflow_id):
        return 'https://%s/#/managers/workflow?id=%s&t=wf' % (self._dart_host, workflow_id)

    @staticmethod
    @retry(wait_fixed=10000, stop_max_attempt_number=12)
    # we experience occasional gmail API issues, so we will retry a few times
    def send_queued_email(args):
        msg = args.get('msg')
        _logger.info("Mailer Thread: message= {to}, {subject}, {body}".format(to=msg.To, subject=msg.Subject, body=msg.Body))
        args.get('mail_sender', lambda(x,y): None)(msg, args.get('debug'))

    @staticmethod
    def send_queued_email_runner(q):
        while True:
            args = q.get()
            try:
                Emailer.send_queued_email(args)
            except Exception as err:
                _logger.error("Failed to send email {0}".format(args.get('msg')))

            q.task_done()

    def send_email(self, subject, body, to, cc=None):
        msg = Message(From=self._from, To=to, Subject=self._env_name + ' - ' + subject, Body=body, CC=cc)
        if self._suppress_send:
            _logger.info('email suppressed: subject=%s' % msg.Subject)
            return

        self._email_queue.put({
            'msg': msg,
            'mail_sender': self._mailer.send,
            'debug': self._debug
        })

    def send_error_email(self, subject, body, to=None):
        cc = None
        if to:
            cc = self._cc_on_error
        else:
            to = self._cc_on_error
        self.send_email(subject, body, to, cc=cc)

    def extract_action_messages(self, action, datastore):
        values = dict(action_id=action.id,
                      action_type_name=action.data.action_type_name,
                      datastore_id=datastore.id,
                      datastore_name=datastore.data.name,
                      entity_link='',
                      action_err_msg=action.data.error_message,
                      action_batch_job_id=action.data.batch_job_id,
                      action_ecs_task_arn=action.data.ecs_task_arn,
                      workflow_id=action.data.workflow_id,
                      workflow_instance_id=action.data.workflow_instance_id,
                      engine_name=action.data.engine_name)

        subject = '{action_status} Dart: action (action_id={action_id}, action_type_name={action_type_name})'
        message = """
                     action (action_id={action_id}, action_type_name={action_type_name}) {action_status}
                     for datastore (datastore_id={datastore_id}, datastore_name={datastore_name})
                     {entity_link}

                     action_err_msg={action_err_msg}

                     workflow_id={workflow_id}, workflow_instance_id={workflow_instance_id}
                     batch_job_id={action_batch_job_id}, action_ecs_task_arn={action_ecs_task_arn}, engine={engine_name}"""

        return (values, subject, message)


    def send_action_failed_email(self, action, datastore):
        values, subject, message = self.extract_action_messages(action, datastore)

        values.update({'action_status': 'FAILED'})
        values.update({'entity_link': self.get_entity_link('actions', action.id)})

        self.send_error_email(
            subject.format(**values),
            dedent(message.format(**values)),
            action.data.on_failure_email
        )


    def send_action_completed_email(self, action, datastore):
        values, subject, message = self.extract_action_messages(action, datastore)

        values.update({'action_status': 'COMPLETED'})

        self.send_email(
            subject.format(**values),
            dedent(message.format(**values)),
            action.data.on_success_email
        )

    def send_workflow_failed_email(self, workflow, wf_instance):
        values = (workflow.id, workflow.data.name, wf_instance.id, self.get_workflow_manager_link(workflow.id),
                  wf_instance.data.error_message)
        self.send_error_email(
            'FAILED Dart: workflow (id=%s, name=%s)' % (workflow.id, workflow.data.name),
            'workflow (id=%s, name=%s) FAILED for instance (id=%s)\n\n%s\n\n%s' % values,
            workflow.data.on_failure_email
        )

    def send_workflow_completed_email(self, workflow, wf_instance):
        values = (workflow.id, workflow.data.name, wf_instance.id, self.get_workflow_manager_link(workflow.id))
        self.send_email(
            'COMPLETED Dart: workflow (id=%s, name=%s)' % (workflow.id, workflow.data.name),
            'workflow (id=%s, name=%s) COMPLETED for instance (id=%s)\n\n%s' % values,
            workflow.data.on_success_email
        )

    def send_workflow_started_email(self, workflow, wf_instance):
        values = (workflow.id, workflow.data.name, wf_instance.id, self.get_workflow_manager_link(workflow.id))
        self.send_email(
            'STARTED Dart: workflow (id=%s, name=%s)' % (workflow.id, workflow.data.name),
            'workflow (id=%s, name=%s) has STARTED: instance (id=%s)\n\n%s' % values,
            workflow.data.on_started_email
        )

    def send_subscription_failed_email(self, subscription):
        values = (subscription.id, subscription.data.name, self.get_entity_link('subscriptions', subscription.id))
        self.send_error_email(
            'FAILED Dart: subscription (id=%s, name=%s)' % (subscription.id, subscription.data.name),
            'subscription (id=%s, name=%s) FAILED\n\n%s' % values,
            subscription.data.on_failure_email
        )

    def send_subscription_completed_email(self, subscription):
        values = (subscription.id, subscription.data.name, self.get_entity_link('subscriptions', subscription.id))
        self.send_email(
            'COMPLETED Dart: subscription (id=%s, name=%s)' % (subscription.id, subscription.data.name),
            'subscription (id=%s, name=%s) COMPLETED\n\n%s' % values,
            subscription.data.on_success_email
        )
