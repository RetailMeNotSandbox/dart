from dart.model.base import dictable, BaseModel
import json

class ActivityEntity(object):
    ACTION = 'action'
    DATASET = 'dataset'
    DATASTORE = 'datastore'
    ENGINE = 'engine'
    EVENT = 'event'
    GRAPH = 'graph'
    SCHEMA = 'schema'
    SUBSCRIPTION = 'subscription'
    TRIGGER = 'trigger'
    WORKFLOW = 'workflow'
    UNKNOWN = 'unknown'

    @staticmethod
    def all():
        return [ActivityEntity.ACTION, ActivityEntity.DATASET, ActivityEntity.DATASTORE, ActivityEntity.ENGINE, ActivityEntity.EVENT,
                ActivityEntity.GRAPH, ActivityEntity.SCHEMA, ActivityEntity.SUBSCRIPTION, ActivityEntity.TRIGGER, ActivityEntity.WORKFLOW]


@dictable
class Accounting(BaseModel):
    def __init__(self, id=None, created=None, user_id='anonymous', state='GET',
                 entity=ActivityEntity.UNKNOWN, params={}, return_code='200', api_version='1', extra=None):
        """
        :type id: str
        :type created: datetime.datetime
        :type user_id: string
        :type state: string
        :type entity: string
        :type params: dict
        :type return_code: string
        :type api_version: string
        :type extra: string
        """
        self.id = id
        self.created = created
        self.user_id = user_id
        self.state = state
        self.entity = entity
        self.params = json.dumps(params)[:1023]
        self.return_code = str(return_code)
        self.api_version = str(api_version)
        self.extra = extra