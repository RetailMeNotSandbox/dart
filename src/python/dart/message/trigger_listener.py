import json
import logging
import traceback

from dart.context.locator import injectable
from dart.message.call import TriggerCall
from dart.model.action import ActionState, OnFailure as ActionOnFailure, Action
from dart.model.datastore import DatastoreState
from dart.model.query import Filter, Operator
from dart.model.workflow import WorkflowInstanceState, WorkflowState, OnFailure as WorkflowOnFailure
from dart.trigger.subscription import subscription_batch_trigger
from dart.trigger.super import super_trigger

_logger = logging.getLogger(__name__)


@injectable
class TriggerListener(object):
    def __init__(self, trigger_broker, trigger_proxy, trigger_service, action_service, datastore_service,
                 workflow_service, emailer, subscription_element_service):
        self._trigger_broker = trigger_broker
        self._trigger_proxy = trigger_proxy
        self._trigger_service = trigger_service
        self._action_service = action_service
        self._datastore_service = datastore_service
        self._workflow_service = workflow_service
        self._emailer = emailer
        self._subscription_element_service = subscription_element_service
        self._handlers = {
            TriggerCall.PROCESS_TRIGGER: self._handle_process_trigger,
            TriggerCall.TRY_NEXT_ACTION: self._handle_try_next_action,
            TriggerCall.COMPLETE_ACTION: self._handle_complete_action,
        }
        self._trigger_processors = {
            name: p.evaluate_message for name, p in trigger_service.trigger_processors().iteritems()
        }

    def await_call(self, wait_time_seconds=20):
        self._trigger_broker.receive_message(self._handle_call, wait_time_seconds)

    def _handle_call(self, message_id, message, previous_handler_failed):
        # CloudWatch Events (scheduled trigger) look like this, and need to be deserialized:
        if 'Message' in message and 'MessageId' in message:
            message = json.loads(message['Message'])

        call = message['call']
        if call not in self._handlers:
            raise Exception('no handler defined for call: %s' % call)
        handler = self._handlers[call]
        try:
            handler(message_id, message, previous_handler_failed)
        except Exception:
            _logger.error(json.dumps(traceback.format_exc()))

    def _handle_process_trigger(self, message_id, message, previous_handler_failed):
        _logger.info("Processing Trigger: message_id={message_id}, message={message}".format(message_id=message_id, message=message))
        if previous_handler_failed:
            _logger.error('previous handler for message id={message_id} failed... see if retrying is possible. message={message}'.\
                          format(message_id=message_id, message=message))
            return
        trigger_type_name = message['trigger_type_name']
        if trigger_type_name not in self._trigger_processors:
            raise Exception('no handler defined for trigger_type_name: {trigger_name}. message_id={message_id}. message={message}'.\
                            format(trigger_name=trigger_type_name, message_id=message_id, message=message))
        handler = self._trigger_processors[trigger_type_name]
        try:
            executed_trigger_ids = handler(message['message'], self._trigger_service)
            for trigger_id in executed_trigger_ids or []:
                self._trigger_proxy.super_trigger_evaluation(trigger_id)

        except Exception:
            _logger.error(json.dumps(traceback.format_exc()))

    def _handle_try_next_action(self, message_id, message, previous_handler_failed):
        if previous_handler_failed:
            _logger.error('previous handler for message id={message_id} failed... see if retrying is possible. message={message}'.format(message_id=message_id, message=message))
            return

        _logger.info("Next Action Trigger: message_id={message_id}, message={message}".format(message_id=message_id, message=message))
        datastore = self._datastore_service.get_datastore(message['datastore_id'])
        running_or_queued_workflow_ids = self._action_service.find_running_or_queued_action_workflow_ids(datastore.id)
        exists_non_workflow_action = self._action_service.exists_running_or_queued_non_workflow_action(datastore.id)
        next_action = self._action_service.find_next_runnable_action(
            datastore_id=datastore.id,
            not_in_workflow_ids=running_or_queued_workflow_ids,
            ensure_workflow_action=exists_non_workflow_action
        )
        if not next_action:
            err_msg = 'datastore (id={datastore_id}) has no actions that can be run at this time. '
            err_msg = err_msg + 'Datastore workflows running/queued = {running_queued}. '
            err_msg = err_msg + 'exists_non_workflow_action={exists_non_workflow_action}. message={message}.'
            _logger.error(err_msg.format(datastore_id=datastore.id,
                                         running_queued=running_or_queued_workflow_ids,
                                         exists_non_workflow_action=exists_non_workflow_action,
                                         message=message))
            return

        assert isinstance(next_action, Action)
        if next_action.data.action_type_name == 'consume_subscription':
            self._subscription_element_service.assign_subscription_elements(next_action)

        self._action_service.update_action_state(next_action, ActionState.QUEUED, next_action.data.error_message)

    def _handle_complete_action(self, message_id, message, previous_handler_failed):
        if previous_handler_failed:
            _logger.error('previous handler for message id=%s failed... see if retrying is possible' % message_id)
            return

        _logger.info("Complete Action Trigger: message_id={message_id}, message={message}".format(message_id=message_id, message=message))
        state = message['action_state']
        action = self._action_service.get_action(message['action_id'])
        assert isinstance(action, Action)
        datastore = self._datastore_service.get_datastore(action.data.datastore_id)
        error_message = message.get('error_message')
        self._action_service.update_action_state(action, state, error_message or action.data.error_message)
        wfid = action.data.workflow_id
        wfiid = action.data.workflow_instance_id
        wf = self._workflow_service.get_workflow(wfid) if wfid else None
        wfi = self._workflow_service.get_workflow_instance(wfiid) if wfiid else None
        callbacks = []
        try_next_action = True
        try:
            if state == ActionState.FAILED:
                callbacks.append(lambda: self._emailer.send_action_failed_email(action, datastore))

                if action.data.on_failure == ActionOnFailure.DEACTIVATE:
                    try_next_action = False
                    if wf and wfi:
                        self._workflow_service.update_workflow_instance_state(wfi, WorkflowInstanceState.FAILED)
                        if wfi.data.retry_num < wf.data.retries_on_failure:
                            retry_num = wfi.data.retry_num + 1
                            callbacks.append(lambda: self._trigger_proxy.trigger_workflow_retry(wfid, retry_num))
                        else:
                            self._workflow_service.update_workflow_state(wf, WorkflowState.INACTIVE)
                            if wf.data.on_failure == WorkflowOnFailure.DEACTIVATE:
                                self._datastore_service.update_datastore_state(datastore, DatastoreState.INACTIVE)
                        f1 = Filter('workflow_instance_id', Operator.EQ, wfiid)
                        f2 = Filter('state', Operator.EQ, ActionState.HAS_NEVER_RUN)
                        for a in self._action_service.query_actions_all(filters=[f1, f2]):
                            error_msg = 'A prior action (id=%s) in this workflow instance failed' % action.id
                            self._action_service.update_action_state(a, ActionState.SKIPPED, error_msg)
                        callbacks.append(lambda: self._emailer.send_workflow_failed_email(wf, wfi))
                    else:
                        self._datastore_service.update_datastore_state(datastore, DatastoreState.INACTIVE)
                else:
                    if wfi and action.data.last_in_workflow:
                        self._handle_complete_workflow(callbacks, wf, wfi, wfid)

            elif state == ActionState.COMPLETED:
                if action.data.on_success_email:
                    callbacks.append(lambda: self._emailer.send_action_completed_email(action, datastore))
                if wfi and action.data.last_in_workflow:
                    self._handle_complete_workflow(callbacks, wf, wfi, wfid)

        finally:
            for f in callbacks:
                f()

        if try_next_action:
            self._trigger_proxy.try_next_action({'datastore_id': datastore.id, 'log_info': message.get('log_info')})

    def _handle_complete_workflow(self, callbacks, wf, wfi, wfid):
        self._workflow_service.update_workflow_instance_state(wfi, WorkflowInstanceState.COMPLETED)
        _logger.info("Trigger Workflow completion:  id={wfid}".format(wfid=wfid))
        self._trigger_proxy.trigger_workflow_completion(wfid)
        self._trigger_subscription_evaluations(wfi.data.trigger_id)
        if wf.data.on_success_email:
            callbacks.append(lambda: self._emailer.send_workflow_completed_email(wf, wfi))

    def _trigger_subscription_evaluations(self, trigger_id):
        if not trigger_id:
            return

        trigger = self._trigger_service.get_trigger(trigger_id, raise_when_missing=False)
        if not trigger:
            return

        if trigger.data.trigger_type_name == subscription_batch_trigger.name:
            self._trigger_proxy.trigger_subscription_evaluation(trigger.id)

        if trigger.data.trigger_type_name == super_trigger.name:
            for ctid in trigger.data.args['completed_trigger_ids']:
                self._trigger_subscription_evaluations(ctid)
