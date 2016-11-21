from flask_login import current_user
from jsonschema import Draft4Validator
from jsonschema.exceptions import best_match
import logging

from dart.model.exception import DartValidationException

_logger = logging.getLogger(__name__)

def apply_defaults(instance, schema):
    if not schema or not instance:
        return

    for prop, subschema in schema.get('properties', {}).iteritems():
        if subschema and 'default' in subschema and instance.get(prop) is None:
            instance[prop] = subschema['default']
        if prop in instance:
            apply_defaults(instance[prop], subschema)

def default_and_validate(model, schema):
    instance = model.to_dict()
    apply_defaults(instance, schema)
    errors = list(Draft4Validator(schema).iter_errors(instance))
    if len(errors) > 0:
        raise DartValidationException(str(best_match(errors)))

    user_id = "anonymous"
    if current_user and current_user.email:
        user_id = current_user.email
    else:
        _logger.debug("No current_user found. using anonymous user id instead.")

    if instance and ('data' in instance) and ("user_id" in instance["data"]):
        instance['data']['user_id'] = user_id
    else:
        _logger.debug("instance['data']['user_id'] do not exist. Skipping setting a user_id.")

    return model.from_dict(instance)


def base_schema(data_json_schema):
    data_json_schema['properties']['user_id'] = {'type': 'string', 'pattern': '^[@.a-zA-Z0-9_-]+$', 'maxLength': 64, 'default': 'unknown', 'readonly': True}
    data_json_schema['required'].append('user_id')
    return {
        'type': 'object',
        'properties': {
            'id': {'type': ['string', 'null'], 'readonly': True},
            'version_id': {'type': ['integer', 'null'], 'readonly': True},
            'created': {'type': ['string', 'null'], 'readonly': True},
            'updated': {'type': ['string', 'null'], 'readonly': True},
            'data': data_json_schema,
        },
        'additionalProperties': False,
        'required': ['data']
    }


def email_list_schema():
    return {
        'x-schema-form': {'type': 'tabarray', 'title': "{{ value || 'email ' + $index }}"},
        'type': 'array',
        'default': [],
        'items': {'type': 'string', 'pattern': '^\\S+@\\S+$'},
        'minItems': 0,
    }


def tag_list_schema():
    return {
        'x-schema-form': {'type': 'tabarray', 'title': "{{ value || 'tag ' + $index }}"},
        'type': 'array',
        'default': [],
        'items': {'type': 'string', 'pattern': '^[a-zA-Z0-9_]+$', 'maxLength': 40},
        'minItems': 0,
    }
