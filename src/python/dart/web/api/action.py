import json
import logging

from flask import Blueprint, request, current_app
from flask.ext.jsontools import jsonapi
from flask.ext.login import login_required
from dart.auth.required_roles import required_roles
from jsonpatch import JsonPatch
from flask_login import current_user

from dart.message.trigger_proxy import TriggerProxy
from dart.model.action import Action, ActionState, OnFailure as ActionOnFailure
from dart.model.query import Filter, Operator
from dart.service.action import ActionService
from dart.service.workflow import WorkflowService
from dart.model.workflow import WorkflowInstanceState, WorkflowState, OnFailure as WorkflowOnFailure
from dart.model.datastore import DatastoreState
from dart.model.workflow import WorkflowInstanceState
from dart.service.datastore import DatastoreService
from dart.service.filter import FilterService
from dart.service.order_by import OrderByService
from dart.web.api.entity_lookup import fetch_model, accounting_track

api_action_bp = Blueprint('api_action', __name__)
_logger = logging.getLogger()

@api_action_bp.route('/datastore/<datastore>/action', methods=['POST'])
@login_required
@fetch_model
@required_roles(['Create'])
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
@required_roles(['Create'])
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
@required_roles(['Edit'])
@accounting_track
@jsonapi
def put_action(action):
    """ :type action: dart.model.action.Action """
    return update_action(action, Action.from_dict(request.get_json()))

@api_action_bp.route('/action/state', methods=['PUT'])
@login_required
@required_roles(['Edit']) # TODO - add a lambda user 
@accounting_track
@jsonapi
def update_action_state():
    """ :type action: dart.model.action.Action """

    # we receive a list of {action_id, action_status, workflow_instance_id/status}
    # We will update the database for each such entry
    try:
        action_status_updates = request.get_json()
        _logger.info("AWS_Batch: extracted json from request: {0}".format(action_status_updates))
    except Exception as err:
        _logger.error("AWS_Batch: Failed to extract json from request")
        return {'result': str(err)}, 500

    try:
        for action_status in action_status_updates:
            # updating the action state
            current_action = action_service().get_action(action_status['action_id'])
            if should_update(action_status['action_status'], current_action.data.state):
                _logger.info("AWS_Batch: Updating action={0} from {1} to state {2}".format(current_action.id, current_action.data.state, action_status['action_status']))
                action_service().update_action_state(current_action, action_status['action_status'], "")

            # if we receive a workflow_instance_id (not empty) then we need to set workflow_instance status.
            # we may need to set workflow and datastore status if they need to be deactivated on failure.
            if action_status.get('workflow_instance_id'):
                wfs = action_status.get('workflow_instance_status')
                wf_instance_status = WorkflowInstanceState.FAILED if (wfs == 'FAILED') else WorkflowInstanceState.COMPLETED
                _logger.info("AWS_Batch: Updating workflow_instance={0} to state {1}".format(action_status.get('workflow_instance_id'), wf_instance_status))

                # Updating workflow_instance with the status sent (success or failure).
                wf_instance = workflow_service().get_workflow_instance(action_status.get('workflow_instance_id'))
                workflow_service().update_workflow_instance_state(wf_instance, wf_instance_status)

                # check if need to deactivate workflow and datastore.
                if wf_instance_status == WorkflowInstanceState.FAILED:
                    workflow_id = wf_instance.data.workflow_id
                    master_workflow = workflow_service().get_workflow(workflow_id)

                    # Failed action with deactivate on_failure should deactivate the current workflow.
                    if current_action.data.on_failure == ActionOnFailure.HALT:
                        _logger.info("AWS_Batch: Action in workflow={0} failed. Halting on failure and remaining in state {2}".format(master_workflow.id, WorkflowState.ACTIVE))
                    elif current_action.data.on_failure == ActionOnFailure.DEACTIVATE:
                        _logger.info("AWS_Batch: Updating workflow={0} to state {2}".format(master_workflow.id, WorkflowState.INACTIVE))
                        workflow_service().update_workflow_state(master_workflow, WorkflowState.INACTIVE)
                        if master_workflow.data.on_failure == WorkflowOnFailure.DEACTIVATE:
                            datastore_id = master_workflow.data.datastore_id
                            _logger.info("AWS_Batch: Updating datastore={0} to state {2}".format(datastore_id, DatastoreState.INACTIVE))
                            datastore = datastore_service().get_datastore(datastore_id)
                            datastore_service().update_datastore_state(datastore, DatastoreState.INACTIVE)
    except Exception as err:
        _logger.error("AWS_Batch: Failed to update action state. err= {0}".format(err))
        return {'result': str(err)}, 501

    # if all pass we send success status (200) otherwise we will try again later.
    return {'result': "OK"}, 200

@api_action_bp.route('/action/<action>', methods=['PATCH'])
@login_required
@fetch_model
@required_roles(['Edit'])
@accounting_track
@jsonapi
def patch_action(action):
    """ :type action: dart.model.action.Action """
    p = JsonPatch(request.get_json())
    return update_action(action, Action.from_dict(p.apply(action.to_dict())))

def should_update(new_state, current_state):
    ''' A new state of action should only be updated if it is a more 'advanced' state.
        The order is PENDING < RUNNABLE < STARTING < RUNNING < COMPLETED < {FAILED|SUCCEEDED}.

        E.g. if current_state is PENDING and new_state is RUNNING then we should update.
             if current_state is SUCCEEDED and new_state is RUNNING then we should NOT update.
    '''
    ORDERED_STATES = {'PENDING': 0, 'RUNNABLE': 1, 'STARTING': 2,
                      'RUNNING': 3, 'COMPLETED': 5, 'FAILED': 6}

    _logger.info("new_state={0}, current_state={1}".format(new_state, current_state))
    if not (new_state in list(ORDERED_STATES.keys())):
        return True

    if not (current_state in list(ORDERED_STATES.keys())):
        return True

    return ORDERED_STATES[current_state] < ORDERED_STATES[new_state]


def update_action(action, updated_action):
    # only allow updating fields that are editable
    sanitized_action = action.copy()
    sanitized_action.data.name = updated_action.data.name
    sanitized_action.data.args = updated_action.data.args
    sanitized_action.data.tags = updated_action.data.tags
    sanitized_action.data.progress = updated_action.data.progress
    sanitized_action.data.order_idx = updated_action.data.order_idx
    sanitized_action.data.parallelization_parents = updated_action.data.parallelization_parents
    sanitized_action.data.parallelization_idx = updated_action.data.parallelization_idx
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
@required_roles(['Delete'])
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


def workflow_service():
    """ :rtype: dart.service.action.WorkflowService """
    return current_app.dart_context.get(WorkflowService)


def datastore_service():
    """ :rtype: dart.service.datastore.DatastoreService """
    return current_app.dart_context.get(DatastoreService)
