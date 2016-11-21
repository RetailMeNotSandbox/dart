from sqlalchemy import cast, desc
from sqlalchemy.dialects.postgresql import JSONB
import uuid

from dart.context.locator import injectable
from dart.model.exception import DartValidationException
from dart.model.orm import TriggerDao
from dart.context.database import db
from dart.model.trigger import TriggerState
from dart.schema.base import default_and_validate
from dart.schema.trigger import trigger_schema
from dart.service.patcher import retry_stale_data, patch_difference
from dart.trigger.base import TriggerProcessor
from dart.util.rand import random_id


@injectable
class TriggerService(object):
    def __init__(self, action_service, datastore_service, workflow_service, manual_trigger_processor,
                 subscription_batch_trigger_processor, workflow_completion_trigger_processor, event_trigger_processor,
                 scheduled_trigger_processor, super_trigger_processor, retry_trigger_processor, filter_service):
        self._action_service = action_service
        self._datastore_service = datastore_service
        self._workflow_service = workflow_service
        self._manual_trigger_processor = manual_trigger_processor
        self._subscription_batch_trigger_processor = subscription_batch_trigger_processor
        self._workflow_completion_trigger_processor = workflow_completion_trigger_processor
        self._event_trigger_processor = event_trigger_processor
        self._scheduled_trigger_processor = scheduled_trigger_processor
        self._super_trigger_processor = super_trigger_processor
        self._retry_trigger_processor = retry_trigger_processor
        self._filter_service = filter_service

        self._trigger_processors = {
            manual_trigger_processor.trigger_type().name: manual_trigger_processor,
            subscription_batch_trigger_processor.trigger_type().name: subscription_batch_trigger_processor,
            workflow_completion_trigger_processor.trigger_type().name: workflow_completion_trigger_processor,
            event_trigger_processor.trigger_type().name: event_trigger_processor,
            scheduled_trigger_processor.trigger_type().name: scheduled_trigger_processor,
            super_trigger_processor.trigger_type().name: super_trigger_processor,
            retry_trigger_processor.trigger_type().name: retry_trigger_processor,
        }

        params_schemas = []
        for name, processor in self._trigger_processors.iteritems():
            params_schemas.append(processor.trigger_type().params_json_schema)
        self._trigger_schemas = [trigger_schema(s) for s in params_schemas]

    def trigger_schemas(self):
        return self._trigger_schemas

    def trigger_processors(self):
        return self._trigger_processors

    def trigger_type_exists(self, trigger_type_name):
        return self.get_trigger_type(trigger_type_name) is not None

    def get_trigger_processor(self, trigger_type_name):
        """ :rtype: dart.model.trigger.TriggerType """
        return self._trigger_processors.get(trigger_type_name)

    def get_trigger_type(self, trigger_type_name):
        """ :rtype: dart.model.trigger.TriggerType """
        return self.get_trigger_processor(trigger_type_name).trigger_type()

    def trigger_types(self):
        return [t.trigger_type() for t in self._trigger_processors.values()]

    def save_trigger(self, trigger, commit_and_initialize=True, flush=False, user_id=None):
        wf_uuid = uuid.uuid4().hex  # to avoid uuid serialization issues
        trigger.data.tags = trigger.data.tags if (trigger.data.tags) else []
        trigger.data.tags.append(wf_uuid)
        if user_id:
            trigger.data.user_id = user_id


        """ :type trigger: dart.model.trigger.Trigger """
        trigger_type_name = trigger.data.trigger_type_name
        if trigger_type_name == self._manual_trigger_processor.trigger_type().name:
            raise DartValidationException('manual triggers cannot be saved')
        if trigger_type_name == self._retry_trigger_processor.trigger_type().name:
            raise DartValidationException('retry triggers cannot be saved')
        trigger_processor = self._trigger_processors.get(trigger_type_name)
        if not trigger_processor:
            raise DartValidationException('unknown trigger_type_name: %s' % trigger_type_name)
        assert isinstance(trigger_processor, TriggerProcessor)
        trigger = default_and_validate(trigger, trigger_schema(trigger_processor.trigger_type().params_json_schema))

        trigger_dao = TriggerDao()
        trigger_dao.id = random_id()
        trigger_dao.data = trigger.data.to_dict()
        db.session.add(trigger_dao)
        if flush:
            db.session.flush()
        trigger = trigger_dao.to_model()
        if commit_and_initialize:
            db.session.commit()
            trigger = trigger_dao.to_model()
            try:
                trigger_processor.initialize_trigger(trigger, self)
            except:
                db.session.delete(trigger_dao)
                db.session.commit()
                raise
        return trigger

    def initialize_trigger(self, trigger):
        """ :type trigger: dart.model.trigger.Trigger """
        trigger_processor = self.get_trigger_processor(trigger.data.trigger_type_name)
        trigger_processor.initialize_trigger(trigger, self)

    @staticmethod
    def get_trigger(trigger_id, raise_when_missing=True):
        """ :rtype: dart.model.trigger.Trigger """
        trigger_dao = TriggerDao.query.get(trigger_id)
        if not trigger_dao and raise_when_missing:
            raise Exception('trigger with id=%s not found' % trigger_id)
        return trigger_dao.to_model() if trigger_dao else None

    @staticmethod
    def find_triggers(trigger_type_name=None, contains_arg=None, limit=None, offset=None, state=TriggerState.ACTIVE):
        query = TriggerService.find_triggers_query(contains_arg, trigger_type_name, state)
        query = query.limit(limit) if limit else query
        query = query.offset(offset) if offset else query
        return [d.to_model() for d in query.all()]

    def find_triggers_count(self):
        return self.find_triggers_query(None, None, None).count()

    @staticmethod
    def find_triggers_query(contains_arg, trigger_type_name, state=TriggerState.ACTIVE):
        query = TriggerDao.query
        if trigger_type_name:
            query = query.filter(TriggerDao.data['trigger_type_name'].astext == trigger_type_name)
        if state:
            query = query.filter(TriggerDao.data['state'].astext == state)
        if contains_arg:
            # we use "op" here because sqlalchemy has a bug in JSONB "contains"
            query = query.filter(TriggerDao.data['args'].op('@>')(cast(contains_arg, JSONB)))
        query = query.order_by(TriggerDao.data['name'])
        return query

    def query_triggers(self, filters, limit=20, offset=0):
        """ :type filters: list[dart.model.query.Filter] """
        query = self._query_trigger_query(filters)
        query = query.limit(limit).offset(offset)
        return [t.to_model() for t in query.all()]

    def query_triggers_count(self, filters):
        """ :type filters: list[dart.model.query.Filter] """
        query = self._query_trigger_query(filters)
        return query.count()

    def _query_trigger_query(self, filters):
        query = TriggerDao.query.order_by(desc(TriggerDao.updated))
        for f in filters:
            query = self._filter_service.apply_filter(f, query, TriggerDao, self._trigger_schemas)
        return query

    def patch_trigger(self, source_trigger, trigger):
        trigger_type_name = trigger.data.trigger_type_name
        if trigger_type_name == self._manual_trigger_processor.trigger_type().name:
            raise DartValidationException('manual triggers cannot be saved')
        if trigger_type_name == self._retry_trigger_processor.trigger_type().name:
            raise DartValidationException('retry triggers cannot be saved')

        trigger_processor = self._trigger_processors.get(trigger_type_name)
        trigger = patch_difference(TriggerDao, source_trigger, trigger)
        return trigger_processor.update_trigger(source_trigger, trigger)

    def default_and_validate_trigger(self, trigger):
        trigger_type_name = trigger.data.trigger_type_name
        trigger_processor = self._trigger_processors.get(trigger_type_name)
        return default_and_validate(trigger, trigger_schema(trigger_processor.trigger_type().params_json_schema))

    @staticmethod
    def update_trigger_workflow_ids(trigger, workflow_ids):
        """ :type trigger: dart.model.trigger.Trigger """
        source_trigger = trigger.copy()
        trigger.data.workflow_ids = workflow_ids
        return patch_difference(TriggerDao, source_trigger, trigger)

    @staticmethod
    def update_trigger_args(trigger, args):
        source_trigger = trigger.copy()
        trigger.data.args = args
        return patch_difference(TriggerDao, source_trigger, trigger)

    @staticmethod
    def update_trigger_extra_data(trigger, extra_data):
        source_trigger = trigger.copy()
        trigger.data.extra_data = extra_data
        return patch_difference(TriggerDao, source_trigger, trigger)

    def delete_trigger(self, trigger_id):
        trigger = TriggerDao.query.get(trigger_id).to_model()
        trigger_handler = self._trigger_processors[trigger.data.trigger_type_name]
        trigger_handler.teardown_trigger(trigger, self)
        self.delete_trigger_retryable(trigger_id)

    @staticmethod
    @retry_stale_data
    def delete_trigger_retryable(trigger_id):
        trigger_dao = TriggerDao.query.get(trigger_id)
        db.session.delete(trigger_dao)
        db.session.commit()

    def trigger_workflow_async(self, workflow_json):
        self._manual_trigger_processor.send_evaluation_message(workflow_json)

    def evaluate_subscription_triggers(self, subscription):
        """ :type subscription: dart.model.subscription.Subscription """
        arg = {'subscription_id': subscription.id}
        for trigger in self.find_triggers(self._subscription_batch_trigger_processor.trigger_type().name, arg):
            self._subscription_batch_trigger_processor.send_evaluation_message(trigger.id)
