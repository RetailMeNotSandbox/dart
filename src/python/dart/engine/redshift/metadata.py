from dart.util.logging_utils import DartLogger

from dart.model.action import ActionType

_logger = DartLogger(__name__)


class RedshiftActionTypes(object):
    start_datastore = ActionType(
        name='start_datastore',
        description='create or restore this Redshift cluster',
        params_json_schema={
            'type': 'object',
            'properties': {
                'snapshot_name': {
                    'type': ['string', 'null'],
                    'default': None,
                    'description': 'the cluster will be restored from this snapshot, or else the latest if one exists'
                                   ' (otherwise, a new cluster will be created)'
                },
            },
            'additionalProperties': False,
        },
    )
    stop_datastore = ActionType(
        name='stop_datastore',
        description='Stops this Redshift cluster and creates a final snapshot',
    )
    create_snapshot = ActionType(
        name='create_snapshot',
        description='create a snapshot of this cluster in the form "dart-datastore-<id>-<YYYYmmddHHMMSS>"',
    )
    execute_sql = ActionType(
        name='execute_sql',
        description='Executes a user defined SQL script',
        params_json_schema={
            'type': 'object',
            'properties': {
                'sql_script': {
                    'type': 'string',
                    'x-schema-form': {'type': 'textarea'},
                    'description': 'The SQL script to be executed'
                },
            },
            'additionalProperties': False,
            'required': ['sql_script'],
        },
    )
    load_dataset = ActionType(
        name='load_dataset',
        description='Copies the dataset from s3 to the datastore',
        params_json_schema={
            'type': 'object',
            'properties': {
                'dataset_id': {'type': 'string', 'description': 'The id of the dataset to load'},
                's3_path_start_prefix_inclusive_date_offset_in_seconds': {'type': ['integer', 'null'], 'default': 0, 'description': 'If specified, the date used in s3 path substitutions will be adjusted by this amount'},
                's3_path_start_prefix_inclusive': {
                    'type': ['string', 'null'],
                    'default': None,
                    'pattern': '^s3://.+$',
                    'description': 'The inclusive s3 path start prefix. The following values (with braces) will be '
                                   'substituted with the appropriate zero-padded values at runtime: {YEAR}, {MONTH}, '
                                   '{DAY}, {HOUR}, {MINUTE}, {SECOND}',
                },
                's3_path_end_prefix_exclusive_date_offset_in_seconds': {'type': ['integer', 'null'], 'default': 0, 'description': 'If specified, the date used in s3 path substitutions will be adjusted by this amount'},
                's3_path_end_prefix_exclusive': {
                    'type': ['string', 'null'],
                    'default': None,
                    'pattern': '^s3://.+$',
                    'description': 'The exclusive s3 path end prefix. The following values (with braces) will be '
                                   'substituted with the appropriate zero-padded values at runtime: {YEAR}, {MONTH}, '
                                   '{DAY}, {HOUR}, {MINUTE}, {SECOND}',
                },
                's3_path_regex_filter_date_offset_in_seconds': {'type': ['integer', 'null'], 'default': 0, 'description': 'If specified, the date used in s3 path substitutions will be adjusted by this amount'},
                's3_path_regex_filter': {
                    'type': ['string', 'null'],
                    'default': None,
                    'description': 'A regex pattern the s3 path must match. The following values (with braces) will be '
                                   'substituted with the appropriate zero-padded values at runtime: {YEAR}, {MONTH}, '
                                   '{DAY}, {HOUR}, {MINUTE}, {SECOND}',
                },
                'target_schema_name': {'type': ['string', 'null'], 'default': 'public', 'pattern': '^[a-zA-Z0-9_]+$', 'description': 'created if absent'},
                'target_table_name': {'type': ['string', 'null'], 'default': None, 'pattern': '^[a-zA-Z0-9_]+$', 'description': 'overrides dataset setting'},
                'target_sort_keys': {
                    'type': 'array',
                    'default': [],
                    'maxItems': 400,
                    'description': 'overrides dataset setting',
                    'x-schema-form': {'type': 'tabarray', 'title': "{{ value || 'sort_key ' + $index }}"},
                    'items': {'type': 'string', 'pattern': '^[a-zA-Z0-9_]+$', 'maxLength': 127}
                },
                'target_distribution_key': {'type': ['string', 'null'], 'default': None, 'pattern': '^[a-zA-Z0-9_]+$', 'description': 'overrides dataset setting'},
                'distribution_style': {'type': 'string', 'default': 'EVEN', 'enum': ['EVEN', 'ALL'], 'description': 'ignored if dist_key is chosen'},
                'sort_keys_interleaved': {'type': ['boolean', 'null'], 'default': False, 'description': 'see AWS Redshift docs'},
                'truncate_columns': {'type': ['boolean', 'null'], 'default': True},
                'max_errors': {'type': ['integer', 'null'], 'default': 0, 'minimum': 0},
                'batch_size': {'type': ['integer', 'null'], 'default': 0, 'minimum': 0},
            },
            'additionalProperties': False,
            'required': ['dataset_id'],
        }
    )
    consume_subscription = ActionType(
        name='consume_subscription',
        description='Consumes the next available dataset subscription elements',
        params_json_schema={
            'type': 'object',
            'properties': {
                'subscription_id': {'type': 'string', 'description': 'The id of the subscription to consume'},
                'target_schema_name': {'type': ['string', 'null'], 'default': 'public', 'pattern': '^[a-zA-Z0-9_]+$', 'description': 'created if absent'},
                'target_table_name': {'type': ['string', 'null'], 'default': None, 'pattern': '^[a-zA-Z0-9_]+$', 'description': 'overrides dataset setting'},
                'target_sort_keys': {
                    'type': 'array',
                    'default': [],
                    'maxItems': 400,
                    'description': 'overrides dataset setting',
                    'x-schema-form': {'type': 'tabarray', 'title': "{{ value || 'sort_key ' + $index }}"},
                    'items': {'type': 'string', 'pattern': '^[a-zA-Z0-9_]+$', 'maxLength': 127}
                },
                'target_distribution_key': {'type': ['string', 'null'], 'default': None, 'pattern': '^[a-zA-Z0-9_]+$', 'description': 'overrides dataset setting'},
                'distribution_style': {'type': 'string', 'default': 'EVEN', 'enum': ['EVEN', 'ALL'], 'description': 'ignored if dist_key is chosen'},
                'sort_keys_interleaved': {'type': ['boolean', 'null'], 'default': False, 'description': 'see AWS Redshift docs'},
                'truncate_columns': {'type': ['boolean', 'null'], 'default': True},
                'max_errors': {'type': ['integer', 'null'], 'default': 0, 'minimum': 0},
                'batch_size': {'type': ['integer', 'null'], 'default': 0, 'minimum': 0},
            },
            'additionalProperties': False,
            'required': ['subscription_id'],
        }
    )
    copy_to_s3 = ActionType(
        name='copy_to_s3',
        description='exports the results of a sql statement to s3',
        params_json_schema={
            'type': 'object',
            'properties': {
                'delimiter': {'type': ['string', 'null'], 'default': '\t', 'description': 'field delimiter'},
                'source_sql_statement': {
                    'type': 'string',
                    "x-schema-form": {"type": "textarea"},
                    'description': 'the SQL SELECT statement to be executed'
                },
                'destination_s3_path': {
                    'type': 'string',
                    'pattern': '^s3://.+$',
                    'description': 'The destination s3 path, e.g. s3://bucket/prefix.  The following values (with braces)'
                                   ' will be substituted with the appropriate zero-padded values at runtime:'
                                   '{YEAR}, {MONTH}, {DAY}, {HOUR}, {MINUTE}, {SECOND}'
                },
                'parallel': {'type': 'boolean', 'default': True, 'description': 'if false, unload sequentially as one file'},
            },
            'additionalProperties': False,
            'required': ['source_sql_statement', 'destination_s3_path'],
        },
    )
    data_check = ActionType(
        name='data_check',
        description='Executes a user defined, SQL data check',
        params_json_schema={
            'type': 'object',
            'properties': {
                'sql_script': {
                    'type': 'string',
                    'x-schema-form': {'type': 'textarea'},
                    'description': 'this SQL should return one row that is true (for "passed") or false (for "failed")'
                },
            },
            'additionalProperties': False,
            'required': ['sql_script'],
        },
    )
