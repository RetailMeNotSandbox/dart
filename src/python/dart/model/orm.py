import json

from flask.ext.jsontools import JsonSerializableBase
from sqlalchemy import BigInteger, Column, Integer, TIMESTAMP, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from dart.model.action import Action
from dart.model.accounting import Accounting

from dart.model.dataset import Dataset
from dart.model.datastore import Datastore
from dart.context.database import db
from dart.model.engine import Engine
from dart.model.event import Event
from dart.model.graph import SubGraphDefinition
from dart.model.message import Message
from dart.model.mutex import Mutex
from dart.model.subscription import Subscription, SubscriptionElement
from dart.model.trigger import Trigger
from dart.model.user import User
from dart.model.api_key import ApiKey
from dart.model.workflow import Workflow, WorkflowInstance
from dart.util.json_util import DartJsonEncoder


class VersionedAuditableSerializable(JsonSerializableBase):
    id = Column(String(length=36), primary_key=True)
    version_id = Column(Integer, index=True, nullable=False, server_default='0')
    created = Column(TIMESTAMP, server_default=db.func.current_timestamp())
    updated = Column(TIMESTAMP, server_default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    __mapper_args__ = {"version_id_col": version_id}
    __modelclass__ = None

    def to_model(self):
        return self.__modelclass__.from_dict(json.loads(json.dumps(self, cls=DartJsonEncoder)))


class VersionedAuditableData(VersionedAuditableSerializable):
    data = Column(JSONB)


class EngineDao(db.Model, VersionedAuditableData):
    __tablename__ = 'engine'
    __modelclass__ = Engine
    name = Column(String(length=255), unique=True, nullable=False)


class SubGraphDefinitionDao(db.Model, VersionedAuditableData):
    __tablename__ = 'subgraph_definition'
    __modelclass__ = SubGraphDefinition


class DatasetDao(db.Model, VersionedAuditableData):
    __tablename__ = 'dataset'
    __modelclass__ = Dataset
    name = Column(String(length=255), unique=True, nullable=False)


class ActionDao(db.Model, VersionedAuditableData):
    __tablename__ = 'action'
    __modelclass__ = Action


class DatastoreDao(db.Model, VersionedAuditableData):
    __tablename__ = 'datastore'
    __modelclass__ = Datastore


class TriggerDao(db.Model, VersionedAuditableData):
    __tablename__ = 'trigger'
    __modelclass__ = Trigger


class WorkflowDao(db.Model, VersionedAuditableData):
    __tablename__ = 'workflow'
    __modelclass__ = Workflow


class WorkflowInstanceDao(db.Model, VersionedAuditableData):
    __tablename__ = 'workflow_instance'
    __modelclass__ = WorkflowInstance


class EventDao(db.Model, VersionedAuditableData):
    __tablename__ = 'event'
    __modelclass__ = Event


class SubscriptionDao(db.Model, VersionedAuditableData):
    __tablename__ = 'subscription'
    __modelclass__ = Subscription


class SubscriptionElementDao(db.Model, VersionedAuditableSerializable):
    __tablename__ = 'subscription_element'
    __modelclass__ = SubscriptionElement
    subscription_id = Column(String(length=36), nullable=False)
    s3_path = Column(String(length=1024), index=True, nullable=False)
    file_size = Column(BigInteger, nullable=False)
    state = Column(String(length=50), nullable=False)
    action_id = Column(String(length=36))
    batch_id = Column(String(length=36))
    processed = Column(TIMESTAMP)


class MessageDao(db.Model, VersionedAuditableSerializable):
    __tablename__ = 'message'
    __modelclass__ = Message
    message_body = Column(Text(), nullable=False)
    instance_id = Column(String(length=32), nullable=False)
    container_id = Column(String(length=256), nullable=False)
    ecs_cluster = Column(String(length=70), nullable=False)
    ecs_container_instance_arn = Column(String(length=256), nullable=False)
    ecs_task_arn = Column(String(length=256), nullable=False)
    state = Column(String(length=50), index=True, nullable=False)


class AccountingDao(db.Model, VersionedAuditableSerializable):
    __tablename__ = 'accounting'
    __modelclass__ = Accounting
    user_id = Column(String(length=128), nullable=False)
    state = Column(String(length=32), nullable=False)
    entity = Column(String(length=32), nullable=False)
    params = Column(String(length=1024), nullable=False)
    return_code = Column(String(length=4), nullable=False)
    api_version = Column(String(length=4), nullable=False)
    extra = Column(String(length=128), nullable=True)

class MutexDao(db.Model, VersionedAuditableSerializable):
    __tablename__ = 'mutex'
    __modelclass__ = Mutex
    name = Column(String(length=255), unique=True, nullable=False)
    state = Column(String(length=50), nullable=False)


class UserDao(db.Model, VersionedAuditableSerializable):
    __tablename__ = 'user'
    __modelclass__ = User
    email = Column(String(length=255), unique=True, nullable=False)
    first_name = Column(String(length=255), unique=False, nullable=True)
    last_name = Column(String(length=255), unique=False, nullable=True)
    is_authenticated = Column(Boolean, server_default='false', nullable=False)
    session_expiration = Column(TIMESTAMP, server_default=db.func.current_timestamp())


class ApiKeyDao(db.Model, VersionedAuditableSerializable):
    __tablename__ = 'api_key'
    __modelclass__ = ApiKey
    user_id = Column(String(length=36), unique=False, nullable=False)
    api_key = Column(String(length=255), unique=True, nullable=False)
    api_secret = Column(String(length=255), unique=False, nullable=False)
