from flask import Blueprint, current_app, request
from flask.ext.jsontools import jsonapi
from flask.ext.login import login_required

from dart.schema.action import action_schema
from dart.schema.dataset import dataset_schema
from dart.schema.datastore import datastore_schema
from dart.schema.engine import engine_schema
from dart.schema.event import event_schema
from dart.schema.dataset_guess import dataset_guess_schema
from dart.schema.subscription import subscription_schema
from dart.schema.trigger import trigger_type_schema, trigger_schema
from dart.schema.workflow import workflow_schema, workflow_instance_schema
from dart.service.action import ActionService
from dart.service.datastore import DatastoreService
from dart.service.engine import EngineService
from dart.service.trigger import TriggerService
from dart.service.workflow import WorkflowService

api_schema_bp = Blueprint('api_schema', __name__)


@api_schema_bp.route('/schema/engine', methods=['GET'])
@login_required
@jsonapi
def get_engine_json_schema():
    return {'results': engine_schema()}


@api_schema_bp.route('/schema/dataset', methods=['GET'])
@login_required
@jsonapi
def get_dataset_json_schema():
    return {'results': dataset_schema()}


@api_schema_bp.route('/schema/dataset/guess', methods=['GET'])
@login_required
@jsonapi
def get_dataset_guess_schema():
    return {'results': dataset_guess_schema()}


@api_schema_bp.route('/schema/engine/<engine_name>/datastore', methods=['GET'])
@login_required
@jsonapi
def get_datastore_json_schema(engine_name):
    engine = engine_service().get_engine_by_name(engine_name)
    if not engine:
        return {'results': 'ERROR', 'error_message': 'unknown engine with name: %s' % engine_name}, 400, None
    return {'results': datastore_schema(engine.data.options_json_schema)}


@api_schema_bp.route('/schema/datastore', methods=['GET'])
@login_required
@jsonapi
def get_datastore_json_schema_empty():
    datastore_id = request.args.get('datastore_id')
    if datastore_id:
        datastore = datastore_service().get_datastore(datastore_id, raise_when_missing=False)
        if not datastore:
            return {'results': 'ERROR', 'error_message': 'no datastore with id: %s' % datastore_id}, 404, None
        return get_datastore_json_schema(datastore.data.engine_name)
    return {'results': datastore_schema(None)}


@api_schema_bp.route('/schema/action', methods=['GET'])
@login_required
@jsonapi
def get_action_json_schema_empty():
    supported_action_type_params_schema = None
    action_id = request.args.get('action_id')
    if action_id:
        action = action_service().get_action(action_id, raise_when_missing=False)
        if not action:
            return {'results': 'ERROR', 'error_message': 'no action with id: %s' % action_id}, 404, None
        engine_name = action.data.engine_name
        engine = engine_service().get_engine_by_name(engine_name)
        for action_type in engine.data.supported_action_types:
            if action_type.name == action.data.action_type_name:
                supported_action_type_params_schema = action_type.params_json_schema
                break
    return {'results': action_schema(supported_action_type_params_schema)}


@api_schema_bp.route('/schema/action/<action_name>', methods=['GET'])
@login_required
@jsonapi
def get_action_json_schema(action_name):
    action_id = request.args.get('action_id')
    datastore_id = request.args.get('datastore_id')
    workflow_id = request.args.get('workflow_id')
    engine_name = request.args.get('engine_name')

    if action_id:
        action = action_service().get_action(action_id, raise_when_missing=False)
        if not action:
            return {'results': 'ERROR', 'error_message': 'no action with id: %s' % action_id}, 404, None
        engine_name = action.data.engine_name

    if workflow_id:
        workflow = workflow_service().get_workflow(workflow_id, raise_when_missing=False)
        if not workflow:
            return {'results': 'ERROR', 'error_message': 'no workflow with id: %s' % workflow_id}, 404, None
        engine_name = workflow.data.engine_name

    if datastore_id:
        datastore = datastore_service().get_datastore(datastore_id, raise_when_missing=False)
        if not datastore:
            return {'results': 'ERROR', 'error_message': 'no datastore with id: %s' % datastore_id}, 404, None
        engine_name = datastore.data.engine_name

    if engine_name:
        engine = engine_service().get_engine_by_name(engine_name)
        if not engine:
            return {'results': 'ERROR', 'error_message': 'unknown engine with name: %s' % engine_name}, 400, None
        for action_type in engine.data.supported_action_types:
            if action_type.name == action_name:
                return {'results': action_schema(action_type.params_json_schema)}
        return {'results': 'ERROR', 'error_message': 'unknown action with name: %s' % action_name}, 400, None

    return {'results': 'ERROR', 'error_message': 'one of datastore_id or workflow_id must be provided'}, 400, None


@api_schema_bp.route('/schema/workflow', methods=['GET'])
@login_required
@jsonapi
def get_workflow_json_schema():
    return {'results': workflow_schema()}


@api_schema_bp.route('/schema/workflow/instance', methods=['GET'])
@login_required
@jsonapi
def get_workflow_instance_json_schema():
    return {'results': workflow_instance_schema()}


@api_schema_bp.route('/schema/trigger_type', methods=['GET'])
@login_required
@jsonapi
def get_trigger_type_json_schema():
    return {'results': trigger_type_schema()}


@api_schema_bp.route('/schema/trigger', methods=['GET'])
@login_required
@jsonapi
def get_trigger_json_schema():
    trigger_type_name = request.args.get('trigger_type_name')
    trigger_id = request.args.get('trigger_id')

    if not trigger_type_name and not trigger_id:
        return {'results': trigger_schema(None)}

    if not trigger_type_name:
        trigger = trigger_service().get_trigger(trigger_id, raise_when_missing=False)
        if not trigger:
            return {'results': 'ERROR', 'error_message': 'trigger not found with id: %s' % trigger_id}, 400, None
        trigger_type_name = trigger.data.trigger_type_name

    trigger_type = trigger_service().get_trigger_type(trigger_type_name)
    if not trigger_type:
        return {'results': 'ERROR', 'error_message': 'unknown trigger_type: %s' % trigger_type_name}, 400, None

    return {'results': trigger_schema(trigger_type.params_json_schema)}


@api_schema_bp.route('/schema/event', methods=['GET'])
@login_required
@jsonapi
def get_event_json_schema():
    return {'results': event_schema()}


@api_schema_bp.route('/schema/subscription', methods=['GET'])
@login_required
@jsonapi
def get_subscription_json_schema():
    return {'results': subscription_schema()}


def engine_service():
    """ :rtype: dart.service.engine.EngineService """
    return current_app.dart_context.get(EngineService)


def action_service():
    """ :rtype: dart.service.action.ActionService """
    return current_app.dart_context.get(ActionService)


def datastore_service():
    """ :rtype: dart.service.datastore.DatastoreService """
    return current_app.dart_context.get(DatastoreService)


def workflow_service():
    """ :rtype: dart.service.workflow.WorkflowService """
    return current_app.dart_context.get(WorkflowService)


def trigger_service():
    """ :rtype: dart.service.trigger.TriggerService """
    return current_app.dart_context.get(TriggerService)
