import json

from flask import Blueprint, request, current_app
from flask.ext.jsontools import jsonapi
from flask.ext.login import login_required

from dart.message.trigger_proxy import TriggerProxy
from dart.model.action import ActionState
from dart.model.engine import Engine, ActionResult, ActionResultState, ActionContext
from dart.model.graph import SubGraphDefinition
from dart.service.action import ActionService
from dart.service.datastore import DatastoreService
from dart.service.engine import EngineService
from dart.service.filter import FilterService
from dart.service.trigger import TriggerService
from dart.service.workflow import WorkflowService
from dart.web.api.entity_lookup import fetch_model, accounting_track

api_engine_bp = Blueprint('api_engine', __name__)


@api_engine_bp.route('/engine', methods=['POST'])
@login_required
@accounting_track
@jsonapi
def post_engine():
    engine = engine_service().save_engine(Engine.from_dict(request.get_json()))
    return {'results': engine.to_dict()}


@api_engine_bp.route('/engine/<engine>', methods=['GET'])
@login_required
@fetch_model
@jsonapi
def get_engine(engine):
    """
    This is the engine API
    Call this api passing a engine id (id column in engine table) and get back its data column.
    E.g. {"name": "no_op_engine", "tags": [], "description": "Helps engineering test dart", "ecs_task_definition": ...}
    """
    return {'results': engine.to_dict()}


@api_engine_bp.route('/engine', methods=['GET'])
@login_required
@jsonapi
def find_engines():
    """
    This is the engine API
    Get back all existing engines.
    """
    limit = int(request.args.get('limit', 20))
    offset = int(request.args.get('offset', 0))
    filters = [filter_service().from_string(f) for f in json.loads(request.args.get('filters', '[]'))]
    engines = engine_service().query_engines(filters, limit, offset)
    return {
        'results': [d.to_dict() for d in engines],
        'limit': limit,
        'offset': offset,
        'total': engine_service().query_engines_count(filters)
    }


@api_engine_bp.route('/engine/<engine>', methods=['PUT'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def put_engine(engine):
    js = request.get_json()
    engineFromJS = Engine.from_dict(js)
    engine = engine_service().update_engine(engine, engineFromJS)
    return {'results': engine.to_dict()}


@api_engine_bp.route('/engine/action/<action>/checkout', methods=['PUT'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def action_checkout(action):
    """ :type action: dart.model.action.Action """
    results = validate_engine_action(action, ActionState.PENDING)
    # (error_response, error_response_code, headers)
    if len(results) == 3:
        return results

    action = workflow_service().action_checkout(action)
    engine, datastore = results
    return {'results': ActionContext(engine, action, datastore).to_dict()}


@api_engine_bp.route('/engine/action/<action>/checkin', methods=['PUT'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def action_checkin(action):
    """ :type action: dart.model.action.Action """
    results = validate_engine_action(action, ActionState.RUNNING)
    # (error_response, error_response_code, headers)
    if len(results) == 3:
        return results

    action_result = ActionResult.from_dict(request.get_json())
    assert isinstance(action_result, ActionResult)
    action_state = ActionState.COMPLETED if action_result.state == ActionResultState.SUCCESS else ActionState.FAILED
    action = workflow_service().action_checkin(action, action_state, action_result.consume_subscription_state)

    error_message = action.data.error_message
    if action_result.state == ActionResultState.FAILURE:
        error_message = action_result.error_message
    trigger_proxy().complete_action(action.id, action_state, error_message)
    return {'results': 'OK'}


def validate_engine_action(action, state):
    if action.data.state != state:
        return {'results': 'ERROR', 'error_message': 'action is no longer %s: %s' % (state, action.id)}, 400, None

    engine_name = action.data.engine_name
    engine = engine_service().get_engine_by_name(engine_name, raise_when_missing=False)
    if not engine:
        return {'results': 'ERROR', 'error_message': 'engine not found: %s' % engine_name}, 404, None

    datastore = datastore_service().get_datastore(action.data.datastore_id)
    if not datastore:
        return {'results': 'ERROR', 'error_message': 'datastore not found: %s' % datastore.id}, 404, None

    return engine, datastore


@api_engine_bp.route('/engine/<engine>', methods=['DELETE'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def delete_engine(engine):
    engine_service().delete_engine(engine)
    return {'results': 'OK'}


@api_engine_bp.route('/engine/<engine>/subgraph_definition', methods=['POST'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def post_subgraph_definition(engine):
    subgraph_definition = engine_service().save_subgraph_definition(
        SubGraphDefinition.from_dict(request.get_json()), engine, trigger_service().trigger_schemas()
    )
    return {'results': subgraph_definition.to_dict()}


@api_engine_bp.route('/subgraph_definition/<subgraph_definition>', methods=['GET'])
@login_required
@fetch_model
@jsonapi
def get_subgraph_definition(subgraph_definition):
    return {'results': subgraph_definition.to_dict()}


@api_engine_bp.route('/engine/<engine>/subgraph_definition', methods=['GET'])
@login_required
@fetch_model
@jsonapi
def get_subgraph_definitions(engine):
    return {'results': engine_service().get_subgraph_definitions(engine.data.name)}


@api_engine_bp.route('/subgraph_definition/<subgraph_definition>', methods=['DELETE'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def delete_subgraph_definition(subgraph_definition):
    engine_service().delete_subgraph_definition(subgraph_definition.id)
    return {'results': 'OK'}


def filter_service():
    """ :rtype: dart.service.filter.FilterService """
    return current_app.dart_context.get(FilterService)


def datastore_service():
    """ :rtype: dart.service.datastore.DatastoreService """
    return current_app.dart_context.get(DatastoreService)


def action_service():
    """ :rtype: dart.service.action.ActionService """
    return current_app.dart_context.get(ActionService)


def workflow_service():
    """ :rtype: dart.service.workflow.WorkflowService """
    return current_app.dart_context.get(WorkflowService)


def trigger_proxy():
    """ :rtype: dart.message.trigger_proxy.TriggerProxy """
    return current_app.dart_context.get(TriggerProxy)


def trigger_service():
    """ :rtype: dart.service.trigger.TriggerService """
    return current_app.dart_context.get(TriggerService)


def engine_service():
    """ :rtype: dart.service.engine.EngineService """
    return current_app.dart_context.get(EngineService)
