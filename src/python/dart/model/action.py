from dart.model.base import BaseModel, dictable


@dictable
class ActionType(BaseModel):
    def __init__(self, name, description=None, params_json_schema=None):
        """
        :type name: str
        :type description: str
        :type params_json_schema: dict
        """
        self.name = name
        self.description = description
        self.params_json_schema = params_json_schema


@dictable
class Action(BaseModel):
    def __init__(self, id=None, version_id=None, created=None, updated=None, data=None):
        """
        :type id: str
        :type version_id: int
        :type created: datetime.datetime
        :type updated: datetime.datetime
        :type data: dart.model.action.ActionData
        """
        self.id = id
        self.version_id = version_id
        self.created = created
        self.updated = updated
        self.data = data


class ActionState(object):
    HAS_NEVER_RUN = 'HAS_NEVER_RUN'
    QUEUED = 'QUEUED'
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    FINISHING = 'FINISHING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    SKIPPED = 'SKIPPED'
    TEMPLATE = 'TEMPLATE'

    @staticmethod
    def all():
        return [ActionState.HAS_NEVER_RUN, ActionState.QUEUED, ActionState.PENDING, ActionState.RUNNING,
                ActionState.FINISHING, ActionState.COMPLETED, ActionState.FAILED, ActionState.SKIPPED,
                ActionState.TEMPLATE]


class OnFailure(object):
    DEACTIVATE = 'DEACTIVATE'
    CONTINUE = 'CONTINUE'

    @staticmethod
    def all():
        return [OnFailure.DEACTIVATE, OnFailure.CONTINUE]


@dictable
class ActionData(BaseModel):
    def __init__(self, name, action_type_name, args=None, state=ActionState.HAS_NEVER_RUN, queued_time=None, start_time=None,
                 end_time=None, progress=None, order_idx=None, error_message=None, on_failure=OnFailure.DEACTIVATE,
                 on_failure_email=None, on_success_email=None, engine_name=None, datastore_id=None, workflow_id=None,
                 workflow_instance_id=None, workflow_action_id=None, first_in_workflow=False, last_in_workflow=False,
                 ecs_task_arn=None, extra_data=None, tags=None, user_id='anonymous', avg_runtime=None, completed_runs=0):
        """
        :type name: str
        :type action_type_name: str
        :type args: dict
        :type state: str
        :type tags: list[str]
        :type queued_time: datetime.datetime
        :type start_time: datetime.datetime
        :type end_time: datetime.datetime
        :type progress: float
        :type order_idx: float
        :type error_message: str
        :type on_failure: str
        :type on_failure_email: list[str]
        :type on_success_email: list[str]
        :type engine_name: str
        :type datastore_id: str
        :type workflow_id: str
        :type workflow_instance_id: str
        :type workflow_action_id: str
        :type first_in_workflow: bool
        :type last_in_workflow: bool
        :type ecs_task_arn: str
        :type extra_data: dict
        :type avg_runtime: datetime.timedelta
        :type completed_runs: int
        """
        self.name = name
        self.action_type_name = action_type_name
        self.args = args
        self.state = state
        self.queued_time = queued_time
        self.start_time = start_time
        self.end_time = end_time
        self.progress = progress
        self.order_idx = order_idx
        self.error_message = error_message
        self.on_failure = on_failure
        self.on_failure_email = on_failure_email or []
        self.on_success_email = on_success_email or []
        self.engine_name = engine_name
        self.datastore_id = datastore_id
        self.workflow_id = workflow_id
        self.workflow_instance_id = workflow_instance_id
        self.workflow_action_id = workflow_action_id
        self.first_in_workflow = first_in_workflow
        self.last_in_workflow = last_in_workflow
        self.ecs_task_arn = ecs_task_arn
        self.extra_data = extra_data
        self.tags = tags or []
        self.user_id = user_id
        self.avg_runtime = avg_runtime
        self.completed_runs = completed_runs
