from sqlalchemy import desc
from dart.context.locator import injectable
from dart.model.datastore import DatastoreState, Datastore
from dart.model.engine import Engine
from dart.model.orm import DatastoreDao
from dart.context.database import db
from dart.schema.base import default_and_validate
from dart.schema.datastore import datastore_schema
from dart.service.patcher import patch_difference, retry_stale_data
from dart.util.rand import random_id
from dart.util.secrets import purge_secrets


@injectable
class DatastoreService(object):
    def __init__(self, trigger_proxy, dart_config, engine_service, filter_service, secrets):
        self._trigger_proxy = trigger_proxy
        self._dart_config = dart_config
        self._engine_service = engine_service
        self._filter_service = filter_service
        self._secrets = secrets

    def save_datastore(self, datastore, commit_and_handle_state_change=True, flush=False):
        """ :type datastore: dart.model.datastore.Datastore """
        schema = self.get_schema(datastore)
        datastore = self.default_and_validate_datastore(datastore, schema)
        datastore.id = random_id()

        secrets = {}
        datastore_dict = datastore.to_dict()
        purge_secrets(datastore_dict, schema, secrets)
        datastore = Datastore.from_dict(datastore_dict)
        for k, v in secrets.iteritems():
            self._secrets.put('dart-datastore-%s-%s' % (datastore.id, k), v)

        self._set_s3_paths(datastore)
        datastore_dao = DatastoreDao()
        datastore_dao.id = datastore.id
        datastore_dao.data = datastore.data.to_dict()
        db.session.add(datastore_dao)
        if flush:
            db.session.flush()
        datastore = datastore_dao.to_model()
        if commit_and_handle_state_change:
            db.session.commit()
            datastore = datastore_dao.to_model()
            self.handle_datastore_state_change(datastore, None, datastore_dao.data['state'])
        return datastore

    def default_and_validate_datastore(self, datastore, schema=None):
        return default_and_validate(datastore, schema or self.get_schema(datastore))

    def get_schema(self, datastore):
        engine = self._engine_service.get_engine_by_name(datastore.data.engine_name)
        assert isinstance(engine, Engine)
        schema = datastore_schema(engine.data.options_json_schema)
        return schema

    def patch_datastore(self, source_datastore, datastore):
        schema = self.get_schema(datastore)
        secrets = {}
        datastore_dict = datastore.to_dict()
        purge_secrets(datastore_dict, schema, secrets)
        datastore = Datastore.from_dict(datastore_dict)
        datastore = patch_difference(DatastoreDao, source_datastore, datastore)
        self.handle_datastore_state_change(datastore, source_datastore.data.state, datastore.data.state)
        return datastore

    def _set_s3_paths(self, datastore):
        """ :type datastore: dart.model.datastore.Datastore """
        s3_root = self._dart_config['dart']['s3_datastores_root'].rstrip('/')
        name = datastore.data.name
        engine_name = datastore.data.engine_name
        ds_id = datastore.id
        datastore.data.s3_artifacts_path = '%s/%s/%s/artifacts/%s' % (s3_root, name, engine_name, ds_id)
        datastore.data.s3_logs_path = '%s/%s/%s/logs/%s' % (s3_root, name, engine_name, ds_id)

    @staticmethod
    def get_datastore(datastore_id, raise_when_missing=True):
        datastore_dao = DatastoreDao.query.get(datastore_id)
        if not datastore_dao and raise_when_missing:
            raise Exception('datastore with id=%s not found' % datastore_id)
        return datastore_dao.to_model() if datastore_dao else None

    def find_datastores(self, limit=20, offset=0):
        query = self.find_datastore_query()
        query = query.limit(limit).offset(offset)
        return [dao.to_model() for dao in query.all()]

    def find_datastores_count(self):
        return self.find_datastore_query().count()

    @staticmethod
    def find_datastore_query():
        return DatastoreDao.query.order_by(DatastoreDao.data['name'])

    @staticmethod
    def find_datastore_count(state, workflow_id):
        return DatastoreDao.query\
            .filter(DatastoreDao.data['state'].astext == state)\
            .filter(DatastoreDao.data['workflow_id'].has_key(workflow_id))\
            .count()

    def query_datastores(self, filters, limit=20, offset=0):
        """ :type filters: list[dart.model.query.Filter] """
        query = self._query_datastore_query(filters)
        query = query.limit(limit).offset(offset)
        return [d.to_model() for d in query.all()]

    def query_datastores_count(self, filters):
        """ :type filters: list[dart.model.query.Filter] """
        query = self._query_datastore_query(filters)
        return query.count()

    def _query_datastore_query(self, filters):
        query = DatastoreDao.query.order_by(desc(DatastoreDao.updated))
        for f in filters:
            query = self._filter_service.apply_filter(f, query, DatastoreDao, self._get_datastore_schemas())
        return query

    def _get_datastore_schemas(self):
        options_schemas = []
        for engine in self._engine_service.query_engines([], 1000, 0):
            options_schemas.append(engine.data.options_json_schema)
        datastore_schemas = [datastore_schema(s) for s in options_schemas]
        return datastore_schemas

    def update_datastore_state(self, datastore, state):
        source_datastore = datastore.copy()
        datastore.data.state = state
        self.handle_datastore_state_change(datastore, source_datastore.data.state, state)
        return patch_difference(DatastoreDao, source_datastore, datastore)

    @staticmethod
    def update_datastore_extra_data(datastore, extra_data):
        source_datastore = datastore.copy()
        datastore.data.extra_data = extra_data
        return patch_difference(DatastoreDao, source_datastore, datastore)

    @staticmethod
    def update_datastore(datastore, host, port, connection_url):
        """ :type datastore: dart.model.datastore.Datastore """
        source_datastore = datastore.copy()
        datastore.data.host = host
        datastore.data.port = port
        datastore.data.connection_url = connection_url
        return patch_difference(DatastoreDao, source_datastore, datastore)

    @staticmethod
    @retry_stale_data
    def delete_datastore(datastore_id):
        datastore_dao = DatastoreDao.query.get(datastore_id)
        db.session.delete(datastore_dao)
        db.session.commit()

    def handle_datastore_state_change(self, datastore, previous_state, updated_state):
        if previous_state != DatastoreState.ACTIVE and updated_state == DatastoreState.ACTIVE:
            self._trigger_proxy.try_next_action({'datastore_id':datastore.id})

    def clone_datastore(self, source_datastore, **data_property_overrides):
        datastore = Datastore.from_dict(source_datastore.to_dict())
        datastore.data.state = DatastoreState.INACTIVE
        datastore.data.host = None
        datastore.data.port = None
        datastore.data.username = None
        datastore.data.password = None
        datastore.data.connection_url = None
        datastore.data.extra_data = None
        self._set_s3_paths(datastore)
        for k, v in data_property_overrides.iteritems():
            setattr(datastore.data, k, v)

        datastore_dao = DatastoreDao()
        datastore_dao.id = random_id()
        datastore_dao.data = datastore.data.to_dict()
        db.session.add(datastore_dao)
        db.session.commit()
        return datastore_dao.to_model()
