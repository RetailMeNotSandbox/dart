from dart.model.workflow import WorkflowState, WorkflowInstanceState, OnFailure
from dart.schema.base import base_schema, email_list_schema, tag_list_schema


def workflow_schema():
    return base_schema({
        'type': 'object',
        'properties': {
            'name': {'type': 'string', 'pattern': '^[a-zA-Z0-9_-]+$', 'maxLength': 50},
            'datastore_id': {'type': 'string'},
            'engine_name': {'type': ['string', 'null'], 'readonly': True},
            'state': {'type': 'string', 'enum': WorkflowState.all(), 'default': WorkflowState.INACTIVE},
            'concurrency': {'type': 'integer', 'default': 1, 'minimum': 1, 'maximum': 10},
            'on_failure': {
                'type': 'string',
                'enum': OnFailure.all(),
                'default': OnFailure.DEACTIVATE,
                'description': 'applies to the datastore'
            },
            'on_failure_email': email_list_schema(),
            'on_success_email': email_list_schema(),
            'on_started_email': email_list_schema(),
            'retries_on_failure': {'type': 'integer', 'default': 0, 'minimum': 0},
            'tags': tag_list_schema(),
            'avg_runtime': {'type': ['string', 'null'], 'readonly': True},
        },
        'additionalProperties': False,
        'required': ['name', 'datastore_id'],
    })


def workflow_instance_schema():
    return base_schema({
        'type': 'object',
        'readonly': True,
        'properties': {
            'workflow_id': {'type': 'string'},
            'datastore_id': {'type': 'string'},
            'engine_name': {'type': 'string'},
            'state': {'type': 'string', 'enum': WorkflowInstanceState.all(), 'default': WorkflowInstanceState.QUEUED},
            'trigger_type': {'type': 'string'},
            'trigger_id': {'type': ['string', 'null']},
            'queued_time': {'type': ['string', 'null']},
            'start_time': {'type': ['string', 'null']},
            'end_time': {'type': ['string', 'null']},
            'retry_num': {'type': 'integer', 'default': 0, 'minimum': 0, 'readonly': True},
            'error_message': {'type': ['string', 'null'], 'readonly': True, "x-schema-form": {"type": "textarea"}},
            'tags': tag_list_schema(),
        },
        'additionalProperties': False,
        'required': [],
    })
