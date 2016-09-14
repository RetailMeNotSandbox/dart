from dart.model.base import dictable, BaseModel


@dictable
class Workflow(BaseModel):
    def __init__(self, id=None, version_id=None, created=None, updated=None, data=None):
        """
        :type id: str
        :type version_id: int
        :type created: datetime.datetime
        :type updated: datetime.datetime
        :type data: dart.model.workflow.WorkflowData
        """
        self.id = id
        self.version_id = version_id
        self.created = created
        self.updated = updated
        self.data = data


class WorkflowState(object):
    ACTIVE = 'ACTIVE'
    INACTIVE = 'INACTIVE'

    @staticmethod
    def all():
        return [WorkflowState.ACTIVE, WorkflowState.INACTIVE]


class OnFailure(object):
    DEACTIVATE = 'DEACTIVATE'
    CONTINUE = 'CONTINUE'

    @staticmethod
    def all():
        return [OnFailure.DEACTIVATE, OnFailure.CONTINUE]


@dictable
class WorkflowData(BaseModel):
    def __init__(self, name, datastore_id=None, engine_name=None, state=WorkflowState.INACTIVE, concurrency=1,
                 on_failure=OnFailure.CONTINUE, on_failure_email=None, on_success_email=None, on_started_email=None,
                 retries_on_failure=0, tags=None, user_id='anonymous', avg_runtime=None):
        """
        :type name: str
        :type datastore_id: str
        :type engine_name: str
        :type state: str
        :type concurrency: int
        :type on_failure: str
        :type on_failure_email: list[str]
        :type on_success_email: list[str]
        :type on_started_email: list[str]
        :type retries_on_failure: int
        :type tags: list[str]
        :type avg_runtime: datetime.timedelta
        """
        self.name = name
        self.datastore_id = datastore_id
        self.engine_name = engine_name
        self.state = state
        self.concurrency = concurrency
        self.on_failure = on_failure
        self.on_failure_email = on_failure_email or []
        self.on_success_email = on_success_email or []
        self.on_started_email = on_started_email or []
        self.retries_on_failure = retries_on_failure
        self.tags = tags or []
        self.user_id = user_id
        self.avg_runtime = avg_runtime


class WorkflowInstanceState(object):
    QUEUED = 'QUEUED'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'

    @staticmethod
    def all():
        return [WorkflowInstanceState.QUEUED, WorkflowInstanceState.RUNNING, WorkflowInstanceState.COMPLETED,
                WorkflowInstanceState.FAILED]


@dictable
class WorkflowInstance(BaseModel):
    def __init__(self, id, version_id, created, updated, data):
        """
        :type id: str
        :type version_id: int
        :type created: datetime.datetime
        :type updated: datetime.datetime
        :type data: dart.model.workflow.WorkflowInstanceData
        """
        self.id = id
        self.version_id = version_id
        self.created = created
        self.updated = updated
        self.data = data


@dictable
class WorkflowInstanceData(BaseModel):
    def __init__(self, workflow_id, datastore_id=None, engine_name=None, state=WorkflowInstanceState.QUEUED,
                 trigger_type=None, trigger_id=None, queued_time=None, start_time=None, end_time=None,
                 retry_num=0, error_message=None, tags=None, user_id='anonymous'):
        """
        :type workflow_id: str
        :type datastore_id: str
        :type engine_name: str
        :type state: str
        :type trigger_type: str
        :type trigger_id: str
        :type queued_time: datetime.datetime
        :type start_time: datetime.datetime
        :type end_time: datetime.datetime
        :type retry_num: int
        :type error_message: str
        :type tags: list[str]
        """
        self.workflow_id = workflow_id
        self.datastore_id = datastore_id
        self.engine_name = engine_name
        self.state = state
        self.trigger_type = trigger_type
        self.trigger_id = trigger_id
        self.queued_time = queued_time
        self.start_time = start_time
        self.end_time = end_time
        self.retry_num = retry_num
        self.error_message = error_message
        self.tags = tags or []
        self.user_id = user_id
