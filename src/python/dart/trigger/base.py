from abc import abstractmethod


class TriggerProcessor(object):
    @abstractmethod
    def trigger_type(self):
        """ :rtype: dart.model.trigger.TriggerType """
        raise NotImplementedError

    @abstractmethod
    def initialize_trigger(self, trigger, trigger_service):
        """ :type trigger: dart.model.trigger.Trigger
            :type trigger_service: dart.service.trigger.TriggerService """
        raise NotImplementedError

    @abstractmethod
    def update_trigger(self, unmodified_trigger, modified_trigger):
        """ :type unmodified_trigger: dart.model.trigger.Trigger
            :type modified_trigger: dart.model.trigger.Trigger """
        raise NotImplementedError

    @abstractmethod
    def evaluate_message(self, message, trigger_service):
        """ :type message: dict
            :type trigger_service: dart.service.trigger.TriggerService
            :rtype: list[str]
            :return the list of trigger ids that were successfully executed/triggered
        """
        raise NotImplementedError

    @abstractmethod
    def teardown_trigger(self, trigger, trigger_service):
        """ :type trigger: dart.model.trigger.Trigger
            :type trigger_service: dart.service.trigger.TriggerService """
        raise NotImplementedError


def execute_trigger(trigger, trigger_type, workflow_service, logger):
    """ :type trigger: dart.model.trigger.Trigger """
    if trigger.data.workflow_ids:
        for workflow_id in trigger.data.workflow_ids:
            try:
                workflow_service.run_triggered_workflow({'workflow_id':workflow_id, 'log_info':{}}, trigger_type, trigger.id)
            except Exception as e:
                values = (workflow_id, trigger.id, e)
                logger.error('Workflow (id=%s) could not be triggered by trigger (id=%s). Exception is: %s' % values)
