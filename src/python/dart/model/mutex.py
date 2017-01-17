from dart.model.base import BaseModel, dictable


class MutexState(object):
    READY = 'READY'
    LOCKED = 'LOCKED'


class Mutexes(object):
    START_ENGINE_TASK = 'START_ENGINE_TASK'
    QUEUE_NEXT_ACTION = 'QUEUE_NEXT_ACTION'

    @staticmethod
    def all():
        return [Mutexes.START_ENGINE_TASK, Mutexes.QUEUE_NEXT_ACTION]

@dictable
class Mutex(BaseModel):
    def __init__(self, id, version_id, created, updated, name, state):
        """
        :type id: str
        :type version_id: int
        :type created: datetime.datetime
        :type updated: datetime.datetime
        :type name: str
        :type state: str
        """
        self.id = id
        self.version_id = version_id
        self.created = created
        self.updated = updated
        self.name = name
        self.state = state
