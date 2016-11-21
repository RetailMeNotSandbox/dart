import json
import logging

import boto3
import jsonpatch

from dart.context.locator import injectable
from dart.model.trigger import TriggerType, TriggerState
from dart.message.call import TriggerCall
from dart.trigger.base import TriggerProcessor, execute_trigger
from dart.model.exception import DartValidationException

_logger = logging.getLogger(__name__)


scheduled_trigger = TriggerType(
    name='scheduled',
    description='Triggering from a scheduler',
    params_json_schema={
        'type': 'object',
        'properties': {
            'cron_pattern': {
                'type': 'string',
                'description': 'The CRON pattern for the schedule. See <a target="_blank" href=' + \
                               '"http://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/ScheduledEvents.html"' + \
                               '>here</a> for correct syntax.'
            },
        },
        'additionalProperties': False,
        'required': ['cron_pattern'],
    }
)


@injectable
class ScheduledTriggerProcessor(TriggerProcessor):
    def __init__(self, workflow_service, dart_config):
        self._workflow_service = workflow_service
        self._trigger_type = scheduled_trigger
        self._dart_config = dart_config

    def trigger_type(self):
        return self._trigger_type

    def initialize_trigger(self, trigger, trigger_service):
        """ :type trigger: dart.model.trigger.Trigger
            :type trigger_service: dart.service.trigger.TriggerService """

        self._validate_aws_cron_expression(trigger.data.args['cron_pattern'])
        # http://boto3.readthedocs.org/en/latest/reference/services/events.html#CloudWatchEvents.Client.put_rule
        client = boto3.client('events')

        client.put_rule(
            Name=self._get_cloudwatch_events_rule_name(trigger),
            ScheduleExpression='cron(%s)' % trigger.data.args['cron_pattern'],
            State='ENABLED',
            Description='scheduled trigger for dart'
        )

        user_id = 'anonymous'
        if trigger.data.user_id:
            user_id = trigger.data.user_id

        if len(trigger.data.tags) > 0:
            workflow_id = trigger.data.tags[0]

        response = client.put_targets(
            Rule=self._get_cloudwatch_events_rule_name(trigger),
            Targets=[
                {
                    'Id': trigger.id,
                    'Arn': self._dart_config['triggers']['scheduled']['cloudwatch_scheduled_events_sns_arn'],
                    'Input': json.dumps({
                        'call': TriggerCall.PROCESS_TRIGGER,
                        'trigger_type_name': self._trigger_type.name,
                        'message': {
                            'trigger_id': trigger.id,
                            'user_id': user_id, # This info is for tracking WF when viewed in cloudwatch rules
                            # logging workflow_id will be auto generated in '/workflow/<workflow>/do-manual-trigger', this one is for future needs.
                            'workflow_id': workflow_id
                        },
                    }),
                }
            ]
        )
        self._check_response(response)
        if trigger.data.state == TriggerState.INACTIVE:
            client.disable_rule(Name=self._get_cloudwatch_events_rule_name(trigger))

    def update_trigger(self, unmodified_trigger, modified_trigger):
        """ :type unmodified_trigger: dart.model.trigger.Trigger
            :type modified_trigger: dart.model.trigger.Trigger """
        client = boto3.client('events')
        patch_list = jsonpatch.make_patch(unmodified_trigger.to_dict(), modified_trigger.to_dict())
        for patch in patch_list:
            if patch['path'] == '/data/state':
                if modified_trigger.data.state == TriggerState.INACTIVE:
                    client.disable_rule(Name=self._get_cloudwatch_events_rule_name(modified_trigger))
                elif modified_trigger.data.state == TriggerState.ACTIVE:
                    client.enable_rule(Name=self._get_cloudwatch_events_rule_name(modified_trigger))
                else:
                    raise Exception('unrecognized trigger state "%s"' % modified_trigger.data.state)
            elif patch['path'] == '/data/args/cron_pattern' and patch['op'] == 'replace':
                client.put_rule(
                    Name=self._get_cloudwatch_events_rule_name(modified_trigger),
                    ScheduleExpression='cron(%s)' % modified_trigger.data.args['cron_pattern'],
                )
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

        execute_trigger(trigger, self._trigger_type, self._workflow_service, _logger)
        return [trigger_id]

    def teardown_trigger(self, trigger, trigger_service):
        """ :type trigger: dart.model.trigger.Trigger
            :type trigger_service: dart.service.trigger.TriggerService """
        rule_name = self._get_cloudwatch_events_rule_name(trigger)
        client = boto3.client('events')
        self._check_response(client.remove_targets(Rule=rule_name, Ids=[trigger.id]))
        client.delete_rule(Name=rule_name)

    @staticmethod
    def _get_cloudwatch_events_rule_name(trigger):
        return 'dart-trigger-%s' % trigger.id

    @staticmethod
    def _check_response(response):
        if response['FailedEntryCount'] > 0:
            error_msg = ''
            for failure in response['FailedEntries']:
                msg = 'Failed on -- Target Id %s, ErrorCode %s, ErrorMessage: %s\n'
                error_msg += msg % (failure['TargetId'], failure['ErrorCode'], failure['ErrorMessage'])
            raise Exception(error_msg)

    @staticmethod
    def _validate_aws_cron_expression(cron_expression):
        # See the Note on: http://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/ScheduledEvents.html
        cron_pattern_split = cron_expression.split()
        if '?' not in [cron_pattern_split[2], cron_pattern_split[4]]:
            raise DartValidationException('CRON Validation Error: Support for specifying both a day-of-week and a '
                                          'day-of-month value is not complete (you must currently use the "?"'
                                          'character in one of these fields).')
