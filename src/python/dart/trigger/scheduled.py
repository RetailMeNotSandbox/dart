import json
import logging

import boto3
import hashlib
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
        rule_name = self._create_rule_if_needed(client, trigger)

        user_id = 'anonymous'
        if trigger.data.user_id:
            user_id = trigger.data.user_id

        if len(trigger.data.tags) > 0:
            workflow_id = trigger.data.tags[0]

        # When a trigger is created in Dart, we should only create a corresponding rule + target if the state is set to
        # ACTIVE.
        if trigger.data.state == TriggerState.ACTIVE:
            target = {
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
            self._add_target_to_rule(client, rule_name, target)

    def update_trigger(self, unmodified_trigger, modified_trigger):
        """ :type unmodified_trigger: dart.model.trigger.Trigger
            :type modified_trigger: dart.model.trigger.Trigger """
        client = boto3.client('events')
        patch_list = jsonpatch.make_patch(unmodified_trigger.to_dict(), modified_trigger.to_dict())
        target = {
            'Id': modified_trigger.id,
            'Arn': self._dart_config['triggers']['scheduled']['cloudwatch_scheduled_events_sns_arn'],
            'Input': json.dumps({
                'call': TriggerCall.PROCESS_TRIGGER,
                'trigger_type_name': self._trigger_type.name,
                'message': {
                    'trigger_id': modified_trigger.id,
                    'user_id': modified_trigger.data.user_id,
                    'workflow_id': modified_trigger.data.workflow_ids[0]
                },
            }),
        }
        for patch in patch_list:
            if patch['path'] == '/data/state':
                if modified_trigger.data.state == TriggerState.ACTIVE:
                    rule_name = self._create_rule_if_needed(client, modified_trigger)
                    self._add_target_to_rule(client, rule_name, target)
                elif modified_trigger.data.state == TriggerState.INACTIVE:
                    self._remove_target_from_prefix(client, unmodified_trigger)
                else:
                    raise Exception('unrecognized trigger state "%s"' % modified_trigger.data.state)
            elif patch['path'] == '/data/args/cron_pattern' and patch['op'] == 'replace':
                self._remove_target_from_prefix(client, unmodified_trigger)
                rule_name = self._create_rule_if_needed(client, modified_trigger)
                self._add_target_to_rule(client, rule_name, target)
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
        client = boto3.client('events')
        self._remove_target_from_prefix(client, trigger)

    def _create_rule_if_needed(self, client, trigger):
        """
        :param client: boto3.session.Session.client
        :param trigger: dart.model.trigger.Trigger
        :return: str
        """
        rule_name = self._next_rule_name(client, trigger)
        try:
            client.describe_rule(Name=rule_name)
        except Exception as e:
            if 'ResourceNotFoundException' in e.message:
                response = client.put_rule(
                    Name=rule_name,
                    ScheduleExpression='cron(%s)' % trigger.data.args['cron_pattern'],
                    State='ENABLED',
                    Description='scheduled trigger for dart'
                )
                _logger.info('Created cloudwatch rule (arn=%s) for trigger (id=%s, cron=%s)' % (response['RuleArn'], trigger.id, trigger.data.args['cron_pattern']))
            else:
                _logger.info('Failed to create cloudwatch rule for trigger (id=%s, cron=%s)' % (trigger.id, trigger.data.args['cron_pattern']))
                raise e
        return rule_name

    def _add_target_to_rule(self, client, rule_name, target):
        """
        :param client: boto3.session.Session.client
        :param rule_name: str
        :param target: str
        """
        response = client.put_targets(
            Rule=rule_name,
            Targets=[target]
        )
        self._check_response(response)
        _logger.info('Created target for trigger (id=%s) on cloudwatch rule (name=%s)' % (target['Id'], rule_name))

    def _next_rule_name(self, client, trigger):
        """
        This method determines what the next rule name should be for new triggers e.g. iff there is a certain cron
        expression that resolves to 'dart-ABCDEF' after hashing and it already has 100 targets, then we create a new
        cloudwatch rule with the name 'dart-ABCDEF-1'.

        :param client: boto3.session.Session.client
        :param trigger: dart.model.trigger.Trigger
        :return: str
        """
        rule_prefix = self._get_cloudwatch_events_rule_prefix(trigger.data.args['cron_pattern'])
        rules = client.list_rules(NamePrefix=rule_prefix)['Rules']
        if not rules:
            return rule_prefix

        for _rule in rules:
            response = client.list_targets_by_rule(Rule=_rule['Name'], Limit=100)
            if len(response['Targets']) < 100:
                return _rule['Name']

        return '%s-%d'% (rule_prefix, len(rules) + 1)

    def _remove_target_from_prefix(self, client, trigger):
        """
        This method goes through all rules with the determined rule prefix to remove the target from the appropriate
        rule. The reason we have to iterate through all rules that match the prefix and can't do a direct removal by
        rule name is because we don't store that anywhere on Dart side on creation.

        :param client: boto3.session.Session.client
        :param trigger: dart.model.trigger.Trigger
        """
        rule_prefix = self._get_cloudwatch_events_rule_prefix(trigger.data.args['cron_pattern'])
        rules = client.list_rules(NamePrefix=rule_prefix)['Rules']
        for _rule in rules:
            response = client.list_targets_by_rule(Rule=_rule['Name'], Limit=100)
            for _target in response['Targets']:
                if _target['Id'] == trigger.id:
                    r = client.remove_targets(Rule=_rule['Name'], Ids=[_target['Id']])
                    self._check_response(r)
                    _logger.info('Deleted target for trigger (id=%s) from cloudwatch rule (name=%s)' % (_target['Id'], _rule['Name']))
                    if len(response['Targets']) == 1:
                        client.delete_rule(Name=_rule['Name'])
                        _logger.info('Deleted cloudwatch rule (name=%s)' % _rule['Name'])
                    return

    @staticmethod
    def _get_cloudwatch_events_rule_name(trigger):
        return 'dart-trigger-%s' % trigger.id

    @staticmethod
    def _get_cloudwatch_events_rule_prefix(cron_expression, hash_size=20):
        """
        This method returns the new naming system for dart triggers. It hashes the cron pattern with sha1 to create new
        cloudwatch rule name. We take only the first 20 chars because the max length allowed for cloudwatch rule name is
        64.

        :param cron_expression: dart.model.trigger.Trigger
        :return: str
        """
        return 'dart-%s' % hashlib.sha1(cron_expression).hexdigest()[:hash_size]

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
