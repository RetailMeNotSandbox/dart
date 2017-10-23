from dart.model.action import ActionState, OnFailure
from dart.schema.base import base_schema, email_list_schema, tag_list_schema, parallelization_parents


def action_schema(supported_action_type_params_schema):
    default_required = ['action_type_name', 'engine_name', 'name']
    return base_schema({
        'type': 'object',
        'properties': {
            'name': {'type': 'string', 'pattern': '^[a-zA-Z0-9_-]+$', 'maxLength': 50},
            'action_type_name': {'type': 'string', 'readonly': True},
            'args': supported_action_type_params_schema or {'type': ['null', 'object'], 'additionalProperties': False, 'properties': {}},
            'state': {'type': 'string', 'enum': ActionState.all(), 'default': ActionState.HAS_NEVER_RUN},
            'tags': tag_list_schema(),
            'queued_time': {'type': ['string', 'null'], 'readonly': True},
            'start_time': {'type': ['string', 'null'], 'readonly': True},
            'end_time': {'type': ['string', 'null'], 'readonly': True},
            'progress': {'type': ['number', 'null'], 'readonly': True},
            'order_idx': {'type': ['number', 'null'], 'minimum': 0.0},
            'parallelization_parents': parallelization_parents(),
            'parallelization_idx': {'type': ['number', 'null'], 'minimum': 0.0},
            'batch_overrides': {
                'vcpus': {'type': ['number', 'null'], 'minimum': 0.0, 'maximum': 1024, 'readonly': True},
                'memory_mb': {'type': ['number', 'null'], 'minimum': 0.0, 'maximum': 61440, 'readonly': True},
                'job_definition': {'type': ['string', 'null'], 'readonly': True},
                'job_queue': {'type': ['string', 'null'], 'readonly': True},
                'job_name': {'type': ['string', 'null'], 'readonly': True}
             },
            'error_message': {'type': ['string', 'null'], 'readonly': True, "x-schema-form": {"type": "textarea"}},
            'on_failure': {
                'type': 'string',
                'enum': OnFailure.all(),
                'default': OnFailure.HALT,
                'description': 'applies to the workflow if this is a workflow action template, otherwise the datastore'
            },
            'on_failure_email': email_list_schema(),
            'on_success_email': email_list_schema(),
            'engine_name': {'type': 'string', 'readonly': True},
            'datastore_id': {'type': ['string', 'null'], 'default': None},
            'workflow_id': {'type': ['string', 'null'], 'default': None},
            'workflow_instance_id': {'type': ['string', 'null'], 'default': None, 'readonly': True},
            'workflow_action_id': {'type': ['string', 'null'], 'default': None, 'readonly': True},
            'first_in_workflow': {'type': ['boolean', 'null'], 'default': False, 'readonly': True},
            'last_in_workflow': {'type': ['boolean', 'null'], 'default': False, 'readonly': True},
            'ecs_task_arn': {'type': ['string', 'null'], 'default': None, 'readonly': True},
            'batch_job_id': {'type': ['string', 'null'], 'default': None, 'readonly': True},
            'extra_data': {'type': ['object', 'null'], 'default': None, 'readonly': True},
            'avg_runtime': {'type': ['string', 'null'], 'readonly': True},
            'completed_runs': {'type': 'integer', 'default': 0, 'readonly': True}
        },
        'additionalProperties': False,
        'required': default_required + ['args'] if supported_action_type_params_schema else default_required
    })
