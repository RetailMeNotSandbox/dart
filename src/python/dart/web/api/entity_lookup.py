import json
from dart.util.logging_utils import DartLogger
import uuid
import traceback
from functools import wraps

from flask import abort, current_app, request, g

from dart.context.locator import injectable
from dart.service.accounting import AccountingService
from dart.web.api.utils import generate_accounting_event

_logger = DartLogger(__name__)

@injectable
class EntityLookupService(object):
    def __init__(self, engine_service, dataset_service, datastore_service, action_service, trigger_service,
                 workflow_service, subscription_service, event_service):
        self._services = {
            'engine': engine_service.get_engine,
            'subgraph_definition': engine_service.get_subgraph_definition,
            'dataset': dataset_service.get_dataset,
            'datastore': datastore_service.get_datastore,
            'action': action_service.get_action,
            'trigger': trigger_service.get_trigger,
            'workflow': workflow_service.get_workflow,
            'workflow_instance': workflow_service.get_workflow_instance,
            'subscription': subscription_service.get_subscription,
            'event': event_service.get_event,
        }

    def unsupported_entity_type(self, entity_type):
        return self._services.get(entity_type) is None

    def get_entity(self, entity_type, id):
        get_func = self._services[entity_type]
        return get_func(id, raise_when_missing=False)


def fetch_model(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        lookup_service = current_app.dart_context.get(EntityLookupService)
        entities_by_type = {}
        for url_param_name, value in kwargs.iteritems():
            if lookup_service.unsupported_entity_type(url_param_name):
                continue
            model = lookup_service.get_entity(url_param_name, value)
            if not model:
                abort(404)
            entities_by_type[url_param_name] = model
        kwargs.update(entities_by_type)
        return f(*args, **kwargs)
    return wrapper


# This decorator's job is to log to the accounting table the activity that took place.
# By default we apply this decorator to non-GET methods only.
# We intentionally run it before the @jsonapi decorator so we can retrieve the return code.
def accounting_track(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        rv = f(*args, **kwargs)

        try:

            return_code = rv.status_code # this is why we wait for the function execution to complete.
            accounting_event = generate_accounting_event(return_code, request)
            AccountingService().save_accounting_event(accounting_event=accounting_event)

        # The choice is not to crash an action (that already completed) in case the logging of the activity event throws
        # an exception in the accounting table fails. This is why we do not rethrow.
        except Exception:
            _logger.error(json.dumps(traceback.format_exc()))

        return rv

    return wrapper



# Generate a new request ID, optionally including an original request ID
def generate_request_id(original_id=''):
    new_id = uuid.uuid4()

    if original_id:
        new_id = "{},{}".format(original_id, new_id)

    return new_id

# Returns the current request ID or a new one if there is none
# In order of preference:
#   * If we've already created a request ID and stored it in the flask.g context local, use that
#   * If a client has passed in the X-Request-Id header, create a new ID with that prepended
#   * Otherwise, generate a request ID and store it in flask.g.request_id
def set_request_id(func_name):
    if getattr(g, 'request_id', None):
        return g.request_id

    headers = request.headers
    original_request_id = headers.get("X-Request-Id")
    new_uuid = generate_request_id(original_request_id)
    g.request_id = new_uuid

    _logger.info("%s: request_id=%s" % (func_name, new_uuid))
    return new_uuid

# This decorator's job is to add a request_id to the flask context (so it can be logged).
def log_request_id(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        set_request_id(f.func_name)
        return f(*args, **kwargs)

    return wrapper