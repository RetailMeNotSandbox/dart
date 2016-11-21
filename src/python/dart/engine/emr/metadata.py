from dart.model.action import ActionType
from dart.model.dataset import FileFormat, RowFormat, Compression


class EmrActionTypes(object):
    start_datastore = ActionType(
        name='start_datastore',
        description='Start this datastore for the first time',
        params_json_schema={
            'type': 'object',
            'properties': {
                'bootstrap_script': {
                    'type': ['string', 'null'],
                    'description': 'The contents of this script will be executed as a bootstrap step',
                    "x-schema-form": {"type": "textarea"}
                },
                'configuration_overrides': {
                    'type': ['string', 'null'],
                    'description':
                        """
                        Optional configuration overrides as a JSON array of Amazon EMR Configuration objects.
                        See the following for a detailed description of the format:
                        http://docs.aws.amazon.com/ElasticMapReduce/latest/ReleaseGuide/emr-configure-apps.html
                        """,
                    "x-schema-form": {"type": "textarea"}
                }
            },
            'additionalProperties': False,
            'required': [],
        }
    )
    terminate_datastore = ActionType(
        name='terminate_datastore',
        description='Permanently destroy this datastore'
    )
    run_hive_script_action = ActionType(
        name='run_hive_script',
        description='Run the provided hive script on the EMR cluster',
        params_json_schema={
            'type': 'object',
            'properties': {
                'script_contents': {
                    'type': 'string',
                    'description': 'The contents of the hive script to execute',
                    "x-schema-form": {"type": "textarea"}
                },
            },
            'additionalProperties': False,
            'required': ['script_contents'],
        }
    )
    run_impala_script_action = ActionType(
        name='run_impala_script',
        description='Run the provided impala script on the EMR cluster',
        params_json_schema={
            'type': 'object',
            'properties': {
                'script_contents': {
                    'type': 'string',
                    'description': 'The contents of the impala script to execute',
                    "x-schema-form": {"type": "textarea"}
                },
            },
            'additionalProperties': False,
            'required': ['script_contents'],
        }
    )
    run_pyspark_script_action = ActionType(
        name='run_pyspark_script',
        description='Run the provided pyspark script on the EMR cluster',
        params_json_schema={
            'type': 'object',
            'properties': {
                'script_contents': {
                    'type': 'string',
                    'description': 'The contents of the pyspark script to execute',
                    "x-schema-form": {"type": "textarea"}
                },
            },
            'additionalProperties': False,
            'required': ['script_contents'],
        }
    )
    copy_hdfs_to_s3_action = ActionType(
        name='copy_hdfs_to_s3',
        description='Copies data at the specified hdfs path to s3',
        params_json_schema={
            'type': 'object',
            'properties': {
                'source_hdfs_path': {'type': 'string', 'pattern': '^hdfs://.+$', 'description': 'The source hdfs path, e.g. hdfs:///user/hive/warehouse/table'},
                'destination_s3_path': {'type': 'string', 'pattern': '^s3://.+$', 'description': 'The destination s3 path, e.g. s3://bucket/prefix'},
            },
            'additionalProperties': False,
            'required': ['source_hdfs_path', 'destination_s3_path'],
        }
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
                'target_table_name': {'type': ['string', 'null'], 'default': None, 'pattern': '^[a-zA-Z0-9_]+$', 'description': 'overrides dataset setting'},
                'target_file_format': {'type': ['string', 'null'], 'enum': FileFormat.all(), 'default': FileFormat.PARQUET, 'description': 'overrides dataset setting'},
                'target_row_format': {'type': ['string', 'null'], 'enum': RowFormat.all(), 'default': RowFormat.NONE, 'description': 'overrides dataset setting'},
                'target_compression': {'type': ['string', 'null'], 'enum': Compression.all(), 'default': Compression.SNAPPY, 'description': 'overrides dataset setting'},
                'target_delimited_by': {'type': ['string', 'null'], 'default': None, 'description': 'overrides dataset setting'},
                'target_quoted_by': {'type': ['string', 'null'], 'default': None, 'description': 'overrides dataset setting'},
                'target_escaped_by': {'type': ['string', 'null'], 'default': None, 'description': 'overrides dataset setting'},
                'target_null_string': {'type': ['string', 'null'], 'default': None, 'description': 'overrides dataset setting'},
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
                'target_table_name': {'type': ['string', 'null'], 'pattern': '^[a-zA-Z0-9_]+$', 'default': None, 'description': 'overrides dataset setting'},
                'target_file_format': {'type': ['string', 'null'], 'enum': FileFormat.all(), 'default': FileFormat.TEXTFILE, 'description': 'overrides dataset setting'},
                'target_row_format': {'type': ['string', 'null'], 'enum': RowFormat.all(), 'default': RowFormat.DELIMITED, 'description': 'overrides dataset setting'},
                'target_compression': {'type': ['string', 'null'], 'enum': Compression.all(), 'default': Compression.GZIP, 'description': 'overrides dataset setting'},
                'target_delimited_by': {'type': ['string', 'null'], 'default': None, 'description': 'overrides dataset setting'},
                'target_quoted_by': {'type': ['string', 'null'], 'default': None, 'description': 'overrides dataset setting'},
                'target_escaped_by': {'type': ['string', 'null'], 'default': None, 'description': 'overrides dataset setting'},
                'target_null_string': {'type': ['string', 'null'], 'default': None, 'description': 'overrides dataset setting'},
            },
            'additionalProperties': False,
            'required': ['subscription_id'],
        }
    )
