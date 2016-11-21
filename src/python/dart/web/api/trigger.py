import json

from flask import Blueprint, request, current_app
from flask.ext.jsontools import jsonapi
from flask.ext.login import login_required
from flask_login import current_user

from jsonpatch import JsonPatch

from dart.model.trigger import Trigger
from dart.service.filter import FilterService
from dart.service.trigger import TriggerService
from dart.service.workflow import WorkflowService
from dart.web.api.entity_lookup import fetch_model, accounting_track


api_trigger_bp = Blueprint('api_trigger', __name__)


@api_trigger_bp.route('/trigger', methods=['POST'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def post_trigger():
    trigger = Trigger.from_dict(request.get_json())
    return {'results': trigger_service().save_trigger(trigger=trigger, user_id=current_user.email).to_dict()}


@api_trigger_bp.route('/trigger/<trigger>', methods=['GET'])
@login_required
@fetch_model
@jsonapi
def get_trigger(trigger):
    return {'results': trigger.to_dict()}


@api_trigger_bp.route('/trigger', methods=['GET'])
@login_required
@jsonapi
def find_triggers():
    limit = int(request.args.get('limit', 20))
    offset = int(request.args.get('offset', 0))
    filters = [filter_service().from_string(f) for f in json.loads(request.args.get('filters', '[]'))]
    triggers = trigger_service().query_triggers(filters, limit, offset)
    return {
        'results': [d.to_dict() for d in triggers],
        'limit': limit,
        'offset': offset,
        'total': trigger_service().query_triggers_count(filters)
    }


@api_trigger_bp.route('/trigger_type', methods=['GET'])
@login_required
@jsonapi
def get_trigger_types():
    limit = int(request.args.get('limit', 20))
    offset = int(request.args.get('offset', 0))
    results = [t.to_dict() for t in trigger_service().trigger_types() if t.name != 'manual']
    return {
        'results': results[offset:(offset + limit)],
        'limit': limit,
        'offset': offset,
        'total': len(results)
    }


@api_trigger_bp.route('/trigger/<trigger>', methods=['PUT'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def put_trigger(trigger):
    """ :type trigger: dart.model.trigger.Trigger """
    return update_trigger(trigger, Trigger.from_dict(request.get_json()))


@api_trigger_bp.route('/trigger/<trigger>', methods=['PATCH'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def patch_trigger(trigger):
    """ :type trigger: dart.model.trigger.Trigger """
    p = JsonPatch(request.get_json())
    return update_trigger(trigger, Trigger.from_dict(p.apply(trigger.to_dict())))


def update_trigger(trigger, updated_trigger):
    # only allow updating fields that are editable
    sanitized_trigger = trigger.copy()
    sanitized_trigger.data.name = updated_trigger.data.name
    sanitized_trigger.data.workflow_ids = updated_trigger.data.workflow_ids
    sanitized_trigger.data.args = updated_trigger.data.args
    sanitized_trigger.data.state = updated_trigger.data.state
    sanitized_trigger.data.tags = updated_trigger.data.tags
    sanitized_trigger.data.extra_data = updated_trigger.data.extra_data

    # revalidate
    sanitized_trigger = trigger_service().default_and_validate_trigger(sanitized_trigger)

    return {'results': trigger_service().patch_trigger(trigger, sanitized_trigger).to_dict()}


@api_trigger_bp.route('/trigger/<trigger>', methods=['DELETE'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def delete_trigger(trigger):
    trigger_service().delete_trigger(trigger.id)
    return {'results': 'OK'}


def filter_service():
    """ :rtype: dart.service.filter.FilterService """
    return current_app.dart_context.get(FilterService)


def trigger_service():
    """ :rtype: dart.service.trigger.TriggerService """
    return current_app.dart_context.get(TriggerService)


def workflow_service():
    """ :rtype: dart.service.workflow.WorkflowService """
    return current_app.dart_context.get(WorkflowService)
