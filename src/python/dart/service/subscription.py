import logging

from datetime import datetime
import boto
from sqlalchemy import insert, literal, not_, func, text, update, cast, String, or_, desc
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm.exc import NoResultFound
from dart.context.locator import injectable
from dart.model.exception import DartValidationException
from dart.model.orm import SubscriptionDao, DatasetDao, SubscriptionElementDao, TriggerDao, WorkflowInstanceDao
from dart.context.database import db
from dart.model.subscription import SubscriptionElementState, SubscriptionState, SubscriptionElementStats
from dart.schema.base import default_and_validate
from dart.schema.subscription import subscription_schema
from dart.service.patcher import patch_difference, retry_stale_data
from dart.trigger.subscription import subscription_batch_trigger
from dart.util.rand import random_id
from dart.util.s3 import yield_s3_keys, get_bucket, get_s3_path


_batch_size = 1000
_logger = logging.getLogger(__name__)


@injectable
class SubscriptionService(object):
    def __init__(self, dataset_service, subscription_proxy, filter_service):
        self._dataset_service = dataset_service
        self._subscription_proxy = subscription_proxy
        self._filter_service = filter_service

    def save_subscription(self, subscription, commit_and_generate=True, flush=False):
        """ :type subscription: dart.model.subscription.Subscription """
        subscription = default_and_validate(subscription, subscription_schema())

        subscription_dao = SubscriptionDao()
        subscription_dao.id = random_id()
        subscription.data.state = SubscriptionState.ACTIVE
        subscription_dao.data = subscription.data.to_dict()
        db.session.add(subscription_dao)
        if flush:
            db.session.flush()
        subscription = subscription_dao.to_model()
        if commit_and_generate:
            db.session.commit()
            subscription = subscription_dao.to_model()
        return subscription

    def generate_subscription_elements(self, subscription):
        self._subscription_proxy.generate_subscription_elements(subscription)

    @staticmethod
    def find_matching_subscriptions(s3_path):
        subscription_daos = SubscriptionDao.query\
            .join(DatasetDao, DatasetDao.id == SubscriptionDao.data['dataset_id'].astext)\
            .filter(SubscriptionDao.data['state'].astext == SubscriptionState.ACTIVE)\
            .filter(
                or_(
                    SubscriptionDao.data['s3_path_start_prefix_inclusive'].astext <= s3_path,
                    SubscriptionDao.data['s3_path_start_prefix_inclusive'] == 'null',
                    not_(SubscriptionDao.data.has_key('s3_path_start_prefix_inclusive')),
                ).self_group()
            )\
            .filter(
                or_(
                    SubscriptionDao.data['s3_path_end_prefix_exclusive'].astext > s3_path,
                    SubscriptionDao.data['s3_path_end_prefix_exclusive'] == 'null',
                    not_(SubscriptionDao.data.has_key('s3_path_end_prefix_exclusive')),
                ).self_group()
            )\
            .filter(
                or_(
                    literal(s3_path).op('~')(cast(SubscriptionDao.data['s3_path_regex_filter'].astext, String)),
                    SubscriptionDao.data['s3_path_regex_filter'] == 'null',
                    not_(SubscriptionDao.data.has_key('s3_path_regex_filter')),
                ).self_group()
            )\
            .filter(literal(s3_path).like(DatasetDao.data['location'].astext + '%'))\
            .all()
        return [s.to_model() for s in subscription_daos]

    @staticmethod
    def get_subscription(subscription_id, raise_when_missing=True):
        subscription_dao = SubscriptionDao.query.get(subscription_id)
        if not subscription_dao and raise_when_missing:
            raise Exception('subscription with id=%s not found' % subscription_id)
        return subscription_dao.to_model() if subscription_dao else None

    def find_subscriptions(self, limit=20, offset=0):
        query = self.find_subscription_query()
        query = query.limit(limit).offset(offset)
        return [dao.to_model() for dao in query.all()]

    def find_subscriptions_count(self):
        return self.find_subscription_query().count()

    @staticmethod
    def find_subscription_query():
        return SubscriptionDao.query.order_by(SubscriptionDao.data['name'])

    def query_subscriptions(self, filters, limit=20, offset=0):
        """ :type filters: list[dart.model.query.Filter] """
        query = self._query_subscription_query(filters)
        query = query.limit(limit).offset(offset)
        return [s.to_model() for s in query.all()]

    def query_subscriptions_count(self, filters):
        """ :type filters: list[dart.model.query.Filter] """
        query = self._query_subscription_query(filters)
        return query.count()

    def _query_subscription_query(self, filters):
        query = SubscriptionDao.query.order_by(desc(SubscriptionDao.updated))
        for f in filters:
            query = self._filter_service.apply_filter(f, query, SubscriptionDao, [subscription_schema()])
        return query

    @staticmethod
    def patch_subscription(source_subscription, subscription):
        subscription = patch_difference(SubscriptionDao, source_subscription, subscription)
        return subscription

    @staticmethod
    def default_and_validate_subscription(subscription):
        return default_and_validate(subscription, subscription_schema())

    @staticmethod
    def update_subscription_state(subscription, state):
        return _update_subscription_state(subscription, state)

    @staticmethod
    def update_subscription_message_id(subscription, message_id):
        """ :type subscription: dart.model.subscription.Subscription """
        source_subscription = subscription.copy()
        subscription.data.message_id = message_id
        return patch_difference(SubscriptionDao, source_subscription, subscription)

    @staticmethod
    @retry_stale_data
    def delete_subscription(subscription_id):
        SubscriptionElementDao.query\
            .filter(SubscriptionElementDao.subscription_id == subscription_id)\
            .delete(synchronize_session='fetch')
        subscription_dao = SubscriptionDao.query.get(subscription_id)
        db.session.delete(subscription_dao)
        db.session.commit()


@injectable
class SubscriptionElementService(object):
    def __init__(self, dataset_service):
        self._dataset_service = dataset_service

    def generate_subscription_elements(self, subscription):
        """ :type subscription: dart.model.subscription.Subscription """
        _update_subscription_state(subscription, SubscriptionState.GENERATING)

        dataset = self._dataset_service.get_dataset(subscription.data.dataset_id)
        conn = boto.connect_s3()
        bucket = get_bucket(conn, dataset.data.location)
        s3_keys = yield_s3_keys(
            bucket,
            dataset.data.location,
            subscription.data.s3_path_start_prefix_inclusive,
            subscription.data.s3_path_end_prefix_exclusive,
            subscription.data.s3_path_regex_filter,
        )
        elements = []
        subscription_element_dict = {}
        for i, key_obj in enumerate(s3_keys):
            sid = subscription.id
            s3_path = get_s3_path(key_obj)
            state = SubscriptionElementState.UNCONSUMED
            now = datetime.now()
            subscription_element_dict = {
                'id': random_id(),
                'version_id': 0,
                'created': now,
                'updated': now,
                'subscription_id': sid,
                's3_path': s3_path,
                'file_size': key_obj.size,
                'state': state
            }
            elements.append(subscription_element_dict)

            batch_size_reached = (i + 1) % _batch_size == 0
            if batch_size_reached:
                self._insert_elements(elements)
                elements = []

        if len(elements) > 0:
            self._insert_elements(elements)

        _update_subscription_state(subscription, SubscriptionState.ACTIVE)

        # Now that the subscription is ACTIVE, s3 events for new files will cause conditional inserts to be
        # performed to keep the subscription up to date.  However, in the time it took for the subscription
        # elements to be generated, s3 events for new objects could have been missed.  So we will do one final
        # s3 list operation (starting with the last inserted key) to fill in the potential gap.
        s3_keys = yield_s3_keys(
            bucket,
            dataset.data.location,
            subscription_element_dict.get('s3_path'),
            subscription.data.s3_path_end_prefix_exclusive,
            subscription.data.s3_path_regex_filter,
        )
        for key_obj in s3_keys:
            self.conditional_insert_subscription_element(subscription, get_s3_path(key_obj), key_obj.size)

    @staticmethod
    def _insert_elements(elements):
        # this will produce one multi-valued insert statement (rather than multiple single inserts)
        db.session.execute(insert(SubscriptionElementDao).values(elements))
        db.session.commit()

    @staticmethod
    def conditional_insert_subscription_element(subscription, s3_path, size):
        # SQLAlchemy does not support conditional inserts as a part of its expression language.  Furthermore,
        # this form of conditional update is required until postgres 9.5 is out and supported by RDS:
        #
        #    http://www.postgresql.org/docs/devel/static/sql-insert.html#SQL-ON-CONFLICT
        #
        sql = """
            INSERT INTO subscription_element (
                id,
                version_id,
                created,
                updated,
                subscription_id,
                s3_path,
                file_size,
                state
            )
            SELECT :id, 0, NOW(), NOW(), :sid, :s3_path, :size, :state
            WHERE NOT EXISTS
                (SELECT NULL FROM subscription_element WHERE subscription_id = :sid AND s3_path = :s3_path)
            """
        sid = subscription.id
        state = SubscriptionElementState.UNCONSUMED
        statement = text(sql).bindparams(id=random_id(), sid=sid, s3_path=s3_path, size=size, state=state)
        results = db.session.execute(statement)
        if results.rowcount != 1:
            db.session.rollback()
            return False
        else:
            db.session.commit()
            return True

    @staticmethod
    def get_subscription_element(subscription_id, s3_path):
        """ :rtype: dart.model.subscription.SubscriptionElement """
        try:
            return SubscriptionElementDao.query\
                .filter(SubscriptionElementDao.subscription_id == subscription_id)\
                .filter(SubscriptionElementDao.s3_path == s3_path)\
                .one()\
                .to_model()
        except NoResultFound:
            values = (subscription_id, s3_path)
            raise DartValidationException('no elements found for subscription (id=%s) key: %s' % values)

    def find_subscription_elements(self, subscription_id, state=SubscriptionElementState.UNCONSUMED, limit=None,
                                   offset=None, gt_s3_path=None, action_id=None, gte_processed=None):
        query = self._find_subscription_elements_query(action_id, gt_s3_path, state, subscription_id, gte_processed)
        query = query.order_by(SubscriptionElementDao.s3_path)
        query = query.limit(limit) if limit else query
        query = query.offset(offset) if offset else query
        return [se.to_model() for se in query.all()]

    def find_subscription_elements_count(self, subscription_id, state=SubscriptionElementState.UNCONSUMED,
                                         gt_s3_path=None, action_id=None, gte_processed=None):
        query = self._find_subscription_elements_query(action_id, gt_s3_path, state, subscription_id, gte_processed)
        return query.count()

    @staticmethod
    def _find_subscription_elements_query(action_id, gt_s3_path, state, subscription_id, gte_processed=None):
        query = SubscriptionElementDao.query
        query = query.filter(SubscriptionElementDao.subscription_id == subscription_id) if subscription_id else query
        query = query.filter(SubscriptionElementDao.state == state) if state else query
        query = query.filter(SubscriptionElementDao.s3_path > gt_s3_path) if gt_s3_path else query
        query = query.filter(SubscriptionElementDao.processed >= gte_processed) if gte_processed else query
        query = query.filter(SubscriptionElementDao.action_id == action_id) if action_id else query
        return query

    @staticmethod
    def get_subscription_element_file_size_sum_and_avg(subscription_id, state=SubscriptionElementState.UNCONSUMED):
        return db.session\
            .query(func.sum(SubscriptionElementDao.file_size), func.avg(SubscriptionElementDao.file_size))\
            .filter(SubscriptionElementDao.subscription_id == subscription_id)\
            .filter(SubscriptionElementDao.state == state)\
            .all()[0] or [0, 0]

    @staticmethod
    def get_subscription_element_stats(subscription_id):
        """ :rtype: dart.model.subscription.SubscriptionElementStats """
        results = db.session\
            .query(
                SubscriptionElementDao.state,
                func.count(),
                func.sum(SubscriptionElementDao.file_size),
            )\
            .filter(SubscriptionElementDao.subscription_id == subscription_id)\
            .group_by(SubscriptionElementDao.state)\
            .all()
        return [SubscriptionElementStats(r[0], int(r[1]), long(r[2])) for r in results]

    @staticmethod
    def reserve_subscription_elements(element_ids):
        # because this is called by the trigger worker (always a single consumer),
        # we shouldn't have to deal with optimistic locking
        db.session.execute(
            update(SubscriptionElementDao)
            .where(SubscriptionElementDao.id.in_(element_ids))
            .values(
                state=SubscriptionElementState.RESERVED,
                batch_id=random_id()
            )
        )
        db.session.commit()

    def assign_subscription_elements(self, action):
        """ :type action: dart.model.action.Action """
        # because this is called by the trigger worker (always a single consumer),
        # we shouldn't have to deal with optimistic locking
        err_msg = 'unexpected action name: %s' % action.data.action_type_name
        assert action.data.action_type_name == 'consume_subscription', err_msg

        wf_instance_id = action.data.workflow_instance_id
        s_id = action.data.args['subscription_id']

        if self._is_subscription_trigger(wf_instance_id):
            state = SubscriptionElementState.RESERVED
            batch_id = self._find_next_batch_id(s_id)
            if not batch_id:
                # no batch_id? something is wonky
                _logger.error('no batch_id found during assignment for triggered subscription (id=%s) elements' % s_id)
                return

        else:
            # no subscription_batch trigger exists, so assign all available
            state = SubscriptionElementState.UNCONSUMED
            batch_id = None

        db.session.execute(
            update(SubscriptionElementDao)
            .where(SubscriptionElementDao.subscription_id == s_id)
            .where(SubscriptionElementDao.state == state)
            .where(SubscriptionElementDao.batch_id == batch_id)
            .values(
                action_id=action.id,
                state=SubscriptionElementState.ASSIGNED
            )
        )
        db.session.commit()

    @staticmethod
    def _find_next_batch_id(s_id):
        batch_id_results = db.session \
            .query(SubscriptionElementDao.batch_id) \
            .filter(SubscriptionElementDao.subscription_id == s_id) \
            .filter(SubscriptionElementDao.state == SubscriptionElementState.RESERVED) \
            .order_by(SubscriptionElementDao.s3_path) \
            .limit(1) \
            .all()
        return batch_id_results[0][0] if len(batch_id_results) > 0 else None

    @staticmethod
    def _subscription_batch_trigger_exists(subscription_id):
        contains_arg = {'subscription_id': subscription_id}
        results = TriggerDao.query \
            .filter(TriggerDao.data['trigger_type_name'].astext == subscription_batch_trigger.name) \
            .filter(TriggerDao.data['state'].astext == SubscriptionState.ACTIVE) \
            .filter(TriggerDao.data['args'].op('@>')(cast(contains_arg, JSONB))) \
            .limit(1) \
            .all()
        return len(results) > 0

    @staticmethod
    def _is_subscription_trigger(workflow_instance_id):
        results = WorkflowInstanceDao.query \
                .filter(WorkflowInstanceDao.id == workflow_instance_id) \
                .filter(WorkflowInstanceDao.data['trigger_type'].astext == subscription_batch_trigger.name) \
                .all()
        return len(results) > 0

    @staticmethod
    def update_subscription_elements_state(action_id, state):
        # because any particular row should never be consumed by more than one worker at a time,
        # we shouldn't have to deal with optimistic locking
        kwargs = {'state': state}
        if state == SubscriptionElementState.CONSUMED:
            kwargs['processed'] = datetime.utcnow()

        db.session.execute(
            update(SubscriptionElementDao)
            .where(SubscriptionElementDao.action_id == action_id)
            .values(**kwargs)
        )
        db.session.commit()


def _update_subscription_state(subscription, state):
    """ :type subscription: dart.model.subscription.Subscription """
    source_subscription = subscription.copy()
    if state == SubscriptionState.QUEUED:
        subscription.data.queued_time = datetime.now()
    if state == SubscriptionState.FAILED:
        subscription.data.failed_time = datetime.now()
    if state == SubscriptionState.GENERATING:
        subscription.data.generating_time = datetime.now()
    if state == SubscriptionState.ACTIVE and subscription.data.state == SubscriptionState.GENERATING:
        subscription.data.initial_active_time = datetime.now()
    subscription.data.state = state
    return patch_difference(SubscriptionDao, source_subscription, subscription)
