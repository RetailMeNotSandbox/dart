import json
from flask import Blueprint, request, current_app
from flask.ext.jsontools import jsonapi
from flask.ext.login import login_required
from jsonpatch import JsonPatch

from dart.model.event import Event
from dart.service.event import EventService
from dart.service.filter import FilterService
from dart.web.api.entity_lookup import fetch_model, accounting_track

api_event_bp = Blueprint('api_event', __name__)


@api_event_bp.route('/event', methods=['POST'])
@login_required
@accounting_track
@jsonapi
def post_event():
    event = event_service().save_event(Event.from_dict(request.get_json()))
    return {'results': event.to_dict()}


@api_event_bp.route('/event/<event>', methods=['GET'])
@login_required
@fetch_model
@jsonapi
def get_event(event):
    return {'results': event.to_dict()}


@api_event_bp.route('/event', methods=['GET'])
@login_required
@jsonapi
def find_events():
    limit = int(request.args.get('limit', 20))
    offset = int(request.args.get('offset', 0))
    filters = [filter_service().from_string(f) for f in json.loads(request.args.get('filters', '[]'))]
    events = event_service().query_events(filters, limit, offset)
    return {
        'results': [d.to_dict() for d in events],
        'limit': limit,
        'offset': offset,
        'total': event_service().query_events_count(filters)
    }


@api_event_bp.route('/event/<event>', methods=['PUT'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def put_event(event):
    """ :type event: dart.model.event.Event """
    return update_event(event, Event.from_dict(request.get_json()))


@api_event_bp.route('/event/<event>', methods=['PATCH'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def patch_event(event):
    """ :type event: dart.model.event.Event """
    p = JsonPatch(request.get_json())
    return update_event(event, Event.from_dict(p.apply(event.to_dict())))


def update_event(event, updated_event):
    # only allow updating fields that are editable
    sanitized_event = event.copy()
    sanitized_event.data.name = updated_event.data.name
    sanitized_event.data.description = updated_event.data.description
    sanitized_event.data.state = updated_event.data.state
    sanitized_event.data.tags = updated_event.data.tags

    # revalidate
    sanitized_event = event_service().default_and_validate_event(sanitized_event)

    return {'results': event_service().patch_event(event, sanitized_event).to_dict()}


@api_event_bp.route('/event/<event>', methods=['DELETE'])
@login_required
@fetch_model
@accounting_track
@jsonapi
def delete_event(event):
    event_service().delete_event(event.id)
    return {'results': 'OK'}


def filter_service():
    """ :rtype: dart.service.filter.FilterService """
    return current_app.dart_context.get(FilterService)


def event_service():
    """ :rtype: dart.service.event.EventService """
    return current_app.dart_context.get(EventService)
