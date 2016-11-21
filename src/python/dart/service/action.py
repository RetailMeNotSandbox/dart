from datetime import datetime, timedelta

from sqlalchemy import Float, func, desc, not_, or_
from sqlalchemy.sql.expression import nullslast

from dart.context.database import db
from dart.context.locator import injectable
from dart.model.action import ActionState, ActionType, Action
from dart.model.engine import Engine
from dart.model.exception import DartValidationException
from dart.model.orm import ActionDao, DatastoreDao
from dart.model.query import Direction, OrderBy
from dart.schema.action import action_schema
from dart.schema.base import default_and_validate
from dart.service.patcher import patch_difference, retry_stale_data
from dart.util.rand import random_id


@injectable
class ActionService(object):
    def __init__(self, engine_service, filter_service, order_by_service):
        self._engine_service = engine_service
        self._filter_service = filter_service
        self._order_by_service = order_by_service

    def save_actions(self, actions, engine_name, datastore=None, commit=True, flush=False):
        """ :type actions: list[dart.model.action.Action]
            :type datastore: dart.model.datastore.Datastore """

        engine = self._engine_service.get_engine_by_name(engine_name)
        assert isinstance(engine, Engine)
        action_types_by_name = {at.name: at for at in engine.data.supported_action_types}

        action_daos = []
        max_order_idx = ActionService._get_max_order_idx(datastore.id) + 1 if datastore else 0
        for action in actions:
            action.data.engine_name = engine_name
            if not action.data.order_idx:
                action.data.order_idx = max_order_idx
            max_order_idx = action.data.order_idx + 1
            action_dao = ActionDao()
            action_dao.id = random_id()

            action_type = action_types_by_name.get(action.data.action_type_name)
            action = self.default_and_validate_action(action, action_type)

            action_dao.data = action.data.to_dict()
            db.session.add(action_dao)
            action_daos.append(action_dao)
        if flush:
            db.session.flush()
        if commit:
            db.session.commit()
        return [a.to_model() for a in action_daos]

    def default_and_validate_action(self, action, action_type=None):
        if not action_type:
            engine = self._engine_service.get_engine_by_name(action.data.engine_name)
            action_types_by_name = {at.name: at for at in engine.data.supported_action_types}
            action_type = action_types_by_name.get(action.data.action_type_name)
        if not action_type:
            raise DartValidationException('unknown action: "%s"' % action.data.action_type_name)
        assert isinstance(action_type, ActionType)
        if not action.data.args:
            action.data.args = {}
        action = default_and_validate(action, action_schema(action_type.params_json_schema))
        return action

    @staticmethod
    def _get_max_order_idx(datastore_id):
        return db.session\
            .query(func.max(ActionDao.data['order_idx'].cast(Float)))\
            .filter(ActionDao.data['datastore_id'].astext == datastore_id).all()[0][0] or 0

    @staticmethod
    def get_action(action_id, raise_when_missing=True):
        action_dao = ActionDao.query.get(action_id)
        if not action_dao and raise_when_missing:
            raise Exception('action with id=%s not found' % action_id)
        return action_dao.to_model() if action_dao else None

    def find_action_count(self, datastore_id=None, states=None, action_type_names=None, gt_order_idx=None, offset=None):
        return self._find_action_query(datastore_id, None, gt_order_idx, None, action_type_names, states, None, None, offset).count()

    def find_actions(self, datastore_id=None, datastore_state=None, states=None, action_type_names=None, gt_order_idx=None, limit=None, workflow_id=None, workflow_instance_id=None, order_by=None, offset=None):
        rs = self._find_action_query(datastore_id, datastore_state, gt_order_idx, limit, action_type_names, states, workflow_id, workflow_instance_id, order_by, offset).all()
        return [a.to_model() for a in rs]

    @staticmethod
    def find_stale_pending_actions():
        query = ActionDao.query\
            .filter(ActionDao.data['state'].astext == ActionState.PENDING)\
            .filter(ActionDao.data['ecs_task_arn'] == 'null')\
            .filter(ActionDao.updated < (datetime.utcnow() - timedelta(minutes=2)))
        return [r.to_model() for r in query.all()]

    @staticmethod
    def find_running_or_queued_action_workflow_ids(datastore_id):
        resultset = db.session\
            .query(func.distinct(ActionDao.data['workflow_id'].astext))\
            .filter(ActionDao.data['datastore_id'].astext == datastore_id)\
            .filter(ActionDao.data['state'].astext.in_([ActionState.RUNNING, ActionState.QUEUED]))\
            .filter(ActionDao.data['workflow_id'] != 'null')\
            .all()
        return [r[0] for r in resultset]

    @staticmethod
    def exists_running_or_queued_non_workflow_action(datastore_id):
        query = ActionDao.query\
            .filter(ActionDao.data['datastore_id'].astext == datastore_id)\
            .filter(ActionDao.data['state'].astext.in_([ActionState.RUNNING, ActionState.QUEUED]))\
            .filter(ActionDao.data['workflow_id'] == 'null')\
            .limit(1)
        return len(list(query.all())) > 0

    @staticmethod
    def find_next_runnable_action(datastore_id, not_in_workflow_ids, ensure_workflow_action):
        query = ActionDao.query\
            .filter(ActionDao.data['datastore_id'].astext == datastore_id)\
            .filter(ActionDao.data['state'].astext == ActionState.HAS_NEVER_RUN)
        if not_in_workflow_ids:
            query = query.filter(
                or_(
                    ActionDao.data['workflow_id'] == 'null',
                    not_(ActionDao.data['workflow_id'].astext.in_(not_in_workflow_ids)),
                ).self_group()
            )
        if ensure_workflow_action:
            query = query.filter(ActionDao.data['workflow_id'] != 'null')
        query = query\
            .order_by(ActionDao.data['order_idx'].cast(Float))\
            .limit(1)
        result = [a for a in query.all()]
        return result[0].to_model() if result else None

    @staticmethod
    def _find_action_query(datastore_id=None, datastore_state=None, gt_order_idx=None, limit=None, action_type_names=None, states=None, workflow_id=None, workflow_instance_id=None, order_by=None, offset=None):
        query = ActionDao.query
        if datastore_id:
            query = query.join(DatastoreDao, DatastoreDao.id == ActionDao.data['datastore_id'].astext)
            query = query.filter(DatastoreDao.id == datastore_id)
            query = query.filter(DatastoreDao.data['state'].astext == datastore_state) if datastore_state else query
        query = query.filter(ActionDao.data['state'].astext.in_(states)) if states else query
        query = query.filter(ActionDao.data['action_type_name'].astext.in_(action_type_names)) if action_type_names else query
        query = query.filter(ActionDao.data['order_idx'].cast(Float) > gt_order_idx) if gt_order_idx else query
        query = query.filter(ActionDao.data['workflow_id'].astext == workflow_id) if workflow_id else query
        query = query.filter(ActionDao.data['workflow_instance_id'].astext == workflow_instance_id) if workflow_instance_id else query

        if order_by:
            for field, direction in order_by:
                if direction == 'desc':
                    query = query.order_by(nullslast(desc(ActionDao.data[field].astext)))
                else:
                    query = query.order_by(nullslast(ActionDao.data[field].astext))
        else:
            query = query.order_by(ActionDao.data['order_idx'].cast(Float))
            query = query.order_by(ActionDao.created)
        query = query.limit(limit) if limit else query
        query = query.offset(offset) if offset else query
        return query

    def query_actions_all(self, filters, order_by=None):
        """ :type filters: list[dart.model.query.Filter]
            :rtype: list[dart.model.action.Action] """
        limit = 20
        offset = 0
        while True:
            results = self.query_actions(filters, limit, offset, order_by)
            if len(results) == 0:
                break
            for e in results:
                yield e
            offset += limit

    def query_actions(self, filters, limit=20, offset=0, order_by=None):
        """ :type filters: list[dart.model.query.Filter] """

        default_order_bys = [OrderBy('updated', Direction.DESC)]
        order_bys = order_by if order_by else default_order_bys

        query = self._query_action_query(filters, order_bys)
        query = query.limit(limit).offset(offset)
        return [a.to_model() for a in query.all()]

    def query_actions_count(self, filters):
        """ :type filters: list[dart.model.query.Filter] """
        query = self._query_action_query(filters)
        return query.count()

    def _query_action_query(self, filters, order_by=None):
        """ :type filters: list[dart.model.query.Filter]
            :type order_by: list[dart.model.query.OrderBy] """
        action_types = []
        for engine in self._engine_service.query_engines([], 1000, 0):
            action_types.extend(engine.data.supported_action_types)
        action_schemas = [action_schema(a.params_json_schema) for a in action_types]

        query = ActionDao.query

        for o in (order_by or []):
            query = self._order_by_service.apply_order_by(o, query, ActionDao, action_schemas)

        for f in filters:
            query = self._filter_service.apply_filter(f, query, ActionDao, action_schemas)

        return query

    def update_action_avg_runtime(self, action_instance, conditional=None):
        """ :type action_instance: dart.model.action.Action """
        if action_instance.data.workflow_action_id is None:
            return
        action = self.get_action(action_instance.data.workflow_action_id)
        source_action = action.copy()
        if action.data.avg_runtime is None:
            action.data.avg_runtime = timedelta()
        runtime = action_instance.data.end_time - action_instance.data.start_time
        action.data.avg_runtime = ((action.data.avg_runtime * action.data.completed_runs) + runtime) / (action.data.completed_runs + 1)
        action.data.completed_runs += 1
        return patch_difference(ActionDao, source_action, action, True, conditional)

    def update_action_state(self, action, state, error_message, conditional=None):
        """ :type action: dart.model.action.Action """
        source_action = action.copy()
        action.data.error_message = error_message
        action.data.state = state
        if state == ActionState.QUEUED:
            action.data.queued_time = datetime.now()
        elif state == ActionState.RUNNING:
            action.data.start_time = datetime.now()
        elif state == ActionState.FAILED:
            action.data.end_time = datetime.now()
        elif state == ActionState.COMPLETED:
            action.data.end_time = datetime.now()
            action.data.progress = 1
            self.update_action_avg_runtime(action)

        return patch_difference(ActionDao, source_action, action, True, conditional)

    @staticmethod
    def update_action_ecs_task_arn(action, ecs_task_arn):
        """ :type action: dart.model.action.Action """
        source_action = action.copy()
        action.data.ecs_task_arn = ecs_task_arn
        return patch_difference(ActionDao, source_action, action)

    @staticmethod
    def update_action(action, progress, extra_data):
        """ :type action: dart.model.action.Action """
        source_action = action.copy()
        action.data.progress = progress
        action.data.extra_data = extra_data
        return patch_difference(ActionDao, source_action, action)

    @staticmethod
    def patch_action(source_action, action):
        return patch_difference(ActionDao, source_action, action)

    @staticmethod
    @retry_stale_data
    def delete_action(action_id):
        action_dao = ActionDao.query.get(action_id)
        db.session.delete(action_dao)
        db.session.commit()

    @staticmethod
    def delete_actions_in_workflow(workflow_id):
        ActionDao.query.filter(ActionDao.data['workflow_id'].astext == workflow_id).delete(False)
        db.session.commit()

    @staticmethod
    def delete_actions_in_workflow_instance(workflow_instance_id):
        ActionDao.query.filter(ActionDao.data['workflow_instance_id'].astext == workflow_instance_id).delete(False)
        db.session.commit()

    def clone_workflow_actions(self, log_info, source_actions, target_datastore_id, **data_property_overrides):
        max_order_idx = self._get_max_order_idx(target_datastore_id)
        for action in source_actions:

            action.data.tags = action.data.tags if (action.data.tags) else []
            if (log_info and log_info.get('wf_uuid')):
                action.data.tags.append(log_info.get('wf_uuid'))

            user_id = 'anonymous'
            if (log_info and log_info.get('user_id')):
                action.data.user_id = log_info.get('user_id')

            max_order_idx += 1
            action.data.order_idx = max_order_idx
            db.session.add(self._clone_workflow_action_to_dao(action, **data_property_overrides))
        db.session.commit()

    @staticmethod
    def _clone_workflow_action_to_dao(source_action, **data_property_overrides):
        action = source_action.copy()
        assert isinstance(action, Action)
        action.data.workflow_action_id = source_action.id
        action.data.state = ActionState.HAS_NEVER_RUN
        action.data.progress = None
        action.data.queued_time = None
        action.data.start_time = None
        action.data.end_time = None
        action.data.error_message = None
        for k, v in data_property_overrides.iteritems():
            setattr(action.data, k, v)
        action_dao = ActionDao()
        action_dao.id = random_id()
        action_dao.data = action.data.to_dict()
        return action_dao
