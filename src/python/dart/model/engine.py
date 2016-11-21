from dart.model.base import BaseModel, dictable


class EngineState(object):
    ACTIVE = 'ACTIVE'
    INACTIVE = 'INACTIVE'

    @staticmethod
    def all():
        return [EngineState.ACTIVE, EngineState.INACTIVE]


@dictable
class Engine(BaseModel):
    def __init__(self, id=None, version_id=None, created=None, updated=None, data=None):
        """
        :type id: str
        :type version_id: int
        :type created: datetime.datetime
        :type updated: datetime.datetime
        :type data: dart.model.engine.EngineData
        """
        self.id = id
        self.version_id = version_id
        self.created = created
        self.updated = updated
        self.data = data


@dictable
class EngineData(object):
    def __init__(self, name, description, options_json_schema, supported_action_types, ecs_task_definition=None,
                 ecs_task_definition_arn=None, tags=None, user_id='anonymous'):
        """
        :type name: str
        :type description: str
        :type options_json_schema: dict
        :type supported_action_types: list[dart.model.action.ActionType]
        :type ecs_task_definition: dict
        :type ecs_task_definition_arn: str
        :type tags: list[str]
        :type user_id: str
        """
        self.name = name
        self.description = description
        self.options_json_schema = options_json_schema
        self.supported_action_types = supported_action_types
        self.ecs_task_definition = ecs_task_definition
        self.ecs_task_definition_arn = ecs_task_definition_arn
        self.tags = tags or []
        self.user_id = user_id


@dictable
class ActionContext(BaseModel):
    def __init__(self, engine=None, action=None, datastore=None):
        """
        :type engine: dart.model.engine.Engine
        :type action: dart.model.action.Action
        :type datastore: dart.model.datastore.Datastore
        """
        self.engine = engine
        self.action = action
        self.datastore = datastore


class ActionResultState(object):
    SUCCESS = 'SUCCESS'
    FAILURE = 'FAILURE'


class ConsumeSubscriptionResultState(object):
    SUCCESS = 'SUCCESS'
    FAILURE = 'FAILURE'


@dictable
class ActionResult(BaseModel):
    def __init__(self, state=None, error_message=None, consume_subscription_state=None):
        """
        :type state: str
        :type error_message: str
        :type consume_subscription_state: str
        """
        self.state = state
        self.error_message = error_message
        self.consume_subscription_state = consume_subscription_state
