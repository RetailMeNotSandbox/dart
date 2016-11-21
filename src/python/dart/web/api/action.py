import json

from flask import Blueprint, request, current_app
from flask.ext.jsontools import jsonapi
from flask.ext.login import login_required
from jsonpatch import JsonPatch
from flask_login import current_user

from dart.message.trigger_proxy import TriggerProxy
from dart.model.action import Action, ActionState
from dart.model.query import Filter, Operator
from dart.service.action import ActionService
from dart.service.datastore import DatastoreService
from dart.service.filter import FilterService
from dart.service.order_by import OrderByService
from dart.web.api.entity_lookup import fetch_model, accounting_track

api_action_bp = Blueprint('api_action', __name__)


@api_action_bp.route('/datastore/<datastore>/action', methods=['POST'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def post_datastore_actions(datastore):
    """ :type datastore: dart.model.datastore.Datastore """
    request_json = request.get_json()
    if not isinstance(request_json, list):
        request_json = [request_json]

    actions = []
    for action_json in request_json:
        action = Action.from_dict(action_json)
        action.data.datastore_id = datastore.id
        action.data.state = ActionState.HAS_NEVER_RUN
        actions.append(action)

    engine_name = datastore.data.engine_name
    saved_actions = [a.to_dict() for a in action_service().save_actions(actions, engine_name, datastore=datastore)]
    trigger_proxy().try_next_action({'datastore_id':datastore.id, 'log_info':{'user_id': current_user.email}})
    return {'results': saved_actions}


@api_action_bp.route('/workflow/<workflow>/action', methods=['POST'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def post_workflow_actions(workflow):
    """ :type workflow: dart.model.workflow.Workflow """
    request_json = request.get_json()
    if not isinstance(request_json, list):
        request_json = [request_json]

    actions = []
    for action_json in request_json:
        action = Action.from_dict(action_json)
        action.data.workflow_id = workflow.id
        action.data.state = ActionState.TEMPLATE
        actions.append(action)

    datastore = datastore_service().get_datastore(workflow.data.datastore_id)
    engine_name = datastore.data.engine_name
    saved_actions = [a.to_dict() for a in action_service().save_actions(actions, engine_name)]
    return {'results': saved_actions}


@api_action_bp.route('/action', methods=['GET'])
@login_required
@jsonapi
def get_datastore_actions():
    limit = int(request.args.get('limit', 20))
    offset = int(request.args.get('offset', 0))
    filters = [filter_service().from_string(f) for f in json.loads(request.args.get('filters', '[]'))]
    order_by = [order_by_service().from_string(f) for f in json.loads(request.args.get('order_by', '[]'))]
    datastore_id = request.args.get('datastore_id')
    workflow_id = request.args.get('workflow_id')
    if datastore_id:
        filters.append(Filter('datastore_id', Operator.EQ, datastore_id))
    if workflow_id:
        filters.append(Filter('workflow_id', Operator.EQ, workflow_id))

    actions = action_service().query_actions(filters, limit, offset, order_by)
    return {
        'results': [a.to_dict() for a in actions],
        'limit': limit,
        'offset': offset,
        'total': action_service().query_actions_count(filters)
    }


@api_action_bp.route('/action/<action>', methods=['GET'])
@login_required
@fetch_model
@jsonapi
def get_action(action):
    return {'results': action.to_dict()}


@api_action_bp.route('/action/<action>', methods=['PUT'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def put_action(action):
    """ :type action: dart.model.action.Action """
    return update_action(action, Action.from_dict(request.get_json()))


@api_action_bp.route('/action/<action>', methods=['PATCH'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def patch_action(action):
    """ :type action: dart.model.action.Action """
    p = JsonPatch(request.get_json())
    return update_action(action, Action.from_dict(p.apply(action.to_dict())))


def update_action(action, updated_action):
    # only allow updating fields that are editable
    sanitized_action = action.copy()
    sanitized_action.data.name = updated_action.data.name
    sanitized_action.data.args = updated_action.data.args
    sanitized_action.data.tags = updated_action.data.tags
    sanitized_action.data.progress = updated_action.data.progress
    sanitized_action.data.order_idx = updated_action.data.order_idx
    sanitized_action.data.on_failure = updated_action.data.on_failure
    sanitized_action.data.on_failure_email = updated_action.data.on_failure_email
    sanitized_action.data.on_success_email = updated_action.data.on_success_email
    sanitized_action.data.extra_data = updated_action.data.extra_data

    # revalidate
    sanitized_action = action_service().default_and_validate_action(sanitized_action)

    return {'results': action_service().patch_action(action, sanitized_action).to_dict()}


@api_action_bp.route('/action/<action>', methods=['DELETE'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def delete_action(action):
    action_service().delete_action(action.id)
    return {'results': 'OK'}


def filter_service():
    """ :rtype: dart.service.filter.FilterService """
    return current_app.dart_context.get(FilterService)


def order_by_service():
    """ :rtype: dart.service.order_by.OrderByService """
    return current_app.dart_context.get(OrderByService)


def trigger_proxy():
    """ :rtype: dart.message.trigger_proxy.TriggerProxy """
    return current_app.dart_context.get(TriggerProxy)


def action_service():
    """ :rtype: dart.service.action.ActionService """
    return current_app.dart_context.get(ActionService)


def datastore_service():
    """ :rtype: dart.service.datastore.DatastoreService """
    return current_app.dart_context.get(DatastoreService)
