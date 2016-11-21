from flask import Blueprint, current_app, request
from flask.ext.jsontools import jsonapi
from flask.ext.login import login_required

from dart.model.graph import GraphEntity, EntityType
from dart.service.action import ActionService
from dart.service.datastore import DatastoreService
from dart.service.graph.resolve import GraphEntityResolverService
from dart.service.graph.entity import GraphEntityService
from dart.service.workflow import WorkflowService
from dart.web.api.entity_lookup import fetch_model, accounting_track

api_graph_bp = Blueprint('api_graph', __name__)


@api_graph_bp.route('/graph/entity_identifiers', methods=['GET'])
@login_required
@jsonapi
def get_graph_entity_identifiers():
    search = request.args.get('search')
    if not search:
        return {'results': 'ERROR', 'error_message': 'search parameter is required'}, 400, None
    return {'results': [e.to_dict() for e in graph_entity_service().get_entity_identifiers(search)]}


@api_graph_bp.route('/graph/action/<action>', methods=['GET'])
@login_required
@fetch_model
@jsonapi
def get_graph_from_action(action):
    """ :type action: dart.model.action.Action """
    entity = GraphEntity('action', action.id, action.data.action_type_name, action.data.state)
    return {'results': graph_entity_service().get_entity_graph(entity).to_dict()}


@api_graph_bp.route('/graph/dataset/<dataset>', methods=['GET'])
@login_required
@fetch_model
@jsonapi
def get_graph_from_dataset(dataset):
    """ :type dataset: dart.model.dataset.Dataset """
    entity = GraphEntity('dataset', dataset.id, dataset.data.name)
    return {'results': graph_entity_service().get_entity_graph(entity).to_dict()}


@api_graph_bp.route('/graph/datastore/<datastore>', methods=['GET'])
@login_required
@fetch_model
@jsonapi
def get_graph_from_datastore(datastore):
    """ :type datastore: dart.model.datastore.Datastore """
    entity = GraphEntity('datastore', datastore.id, datastore.data.name, datastore.data.state)
    return {'results': graph_entity_service().get_entity_graph(entity).to_dict()}


@api_graph_bp.route('/graph/event/<event>', methods=['GET'])
@login_required
@fetch_model
@jsonapi
def get_graph_from_event(event):
    """ :type event: dart.model.event.Event """
    entity = GraphEntity('event', event.id, event.data.name, event.data.state)
    return {'results': graph_entity_service().get_entity_graph(entity).to_dict()}


@api_graph_bp.route('/graph/subscription/<subscription>', methods=['GET'])
@login_required
@fetch_model
@jsonapi
def get_graph_from_subscription(subscription):
    """ :type subscription: dart.model.subscription.Subscription """
    entity = GraphEntity('subscription', subscription.id, subscription.data.name, subscription.data.state)
    return {'results': graph_entity_service().get_entity_graph(entity).to_dict()}


@api_graph_bp.route('/graph/trigger/<trigger>', methods=['GET'])
@login_required
@fetch_model
@jsonapi
def get_graph_from_trigger(trigger):
    """ :type trigger: dart.model.trigger.Trigger """
    entity = GraphEntity('trigger', trigger.id, trigger.data.name, trigger.data.state, trigger.data.trigger_type_name)
    return {'results': graph_entity_service().get_entity_graph(entity).to_dict()}


@api_graph_bp.route('/graph/workflow/<workflow>', methods=['GET'])
@login_required
@fetch_model
@jsonapi
def get_graph_from_workflow(workflow):
    """ :type workflow: dart.model.workflow.Workflow """
    entity = GraphEntity('workflow', workflow.id, workflow.data.name, workflow.data.state)
    return {'results': graph_entity_service().get_entity_graph(entity).to_dict()}


@api_graph_bp.route('/graph/sub_graph', methods=['GET'])
@login_required
@jsonapi
def get_sub_graphs():
    related_type = request.args.get('related_type')
    related_id = request.args.get('related_id')
    related_engine_name = request.args.get('engine_name')

    if not related_engine_name:
        if related_id and related_type == EntityType.workflow:
            workflow = workflow_service().get_workflow(related_id, raise_when_missing=False)
            if workflow is None:
                return {'results': 'ERROR', 'error_message': 'workflow with id=%s not found' % related_id}, 404, None
            datastore_id = workflow.data.datastore_id
            datastore = datastore_service().get_datastore(datastore_id, raise_when_missing=False)
            if datastore is None:
                return {'results': 'ERROR', 'error_message': 'datastore with id=%s not found' % datastore_id}, 404, None
            related_engine_name = datastore.data.engine_name

        if related_id and related_type == EntityType.datastore:
            datastore = datastore_service().get_datastore(related_id, raise_when_missing=False)
            if datastore is None:
                return {'results': 'ERROR', 'error_message': 'datastore with id=%s not found' % related_id}, 404, None
            related_engine_name = datastore.data.engine_name

        if related_id and related_type == EntityType.action:
            action = action_service().get_action(related_id, raise_when_missing=False)
            if action is None:
                return {'results': 'ERROR', 'error_message': 'action with id=%s not found' % related_id}, 404, None
            related_engine_name = action.data.engine_name

    sub_graph_map = graph_entity_service().get_sub_graphs(related_type, related_engine_name)
    return {'results': {engine_name: [s.to_dict() for s in sub_graphs] for engine_name, sub_graphs in sub_graph_map.iteritems()}}


@api_graph_bp.route('/graph/sub_graph', methods=['POST'])
@login_required
@accounting_track
@jsonapi
def post_entity_map():
    results, error = graph_entity_resolver_service().save_entities(request.get_json(), request.args.get('debug'))
    if error:
        return {'results': 'ERROR', 'error_message': str(error)}, 400, None
    return {'results': {k: v.to_dict() for k, v in results.iteritems()}}


def graph_entity_resolver_service():
    """ :rtype: dart.service.entity.GraphEntityResolverService """
    return current_app.dart_context.get(GraphEntityResolverService)


def datastore_service():
    """ :rtype: dart.service.datastore.DatastoreService """
    return current_app.dart_context.get(DatastoreService)


def workflow_service():
    """ :rtype: dart.service.workflow.WorkflowService """
    return current_app.dart_context.get(WorkflowService)


def action_service():
    """ :rtype: dart.service.action.ActionService """
    return current_app.dart_context.get(ActionService)


def graph_entity_service():
    """ :rtype: dart.service.graph.GraphEntityService """
    return current_app.dart_context.get(GraphEntityService)
