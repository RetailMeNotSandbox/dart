import logging

from dart.model.action import ActionType

_logger = logging.getLogger(__name__)


class S3ActionTypes(object):
    copy = ActionType(
        name='copy',
        description='Accomplishes s3 source to s3 destination copy, giving the destination bucket owner full control',
        params_json_schema={
            'type': 'object',
            'properties': {
                'from_path': {'type': 'string', 'pattern': '^s3://.+$', 'description': 'The source s3 file path'},
                'to_path': {'type': 'string', 'pattern': '^s3://.+$', 'description': 'The destination s3 file path'},
                'recursive': {'type': ['boolean', 'null'], 'default': True, 'description': 'Performs recursive copy of source to destination'},
                'additionalProperties': False,
                'required': ['from_path', 'to_path']
            }
        }
    )

    data_check = ActionType(
        name='data_check',
        description='A data check that passes if an s3 key/file exists that matches the specified requirements',
        params_json_schema={
            'type': 'object',
            'properties': {
                's3_path_prefix': {
                    'type': ['string', 'null'],
                    'pattern': '^s3://.+$',
                    'description': 'The s3 path prefix where at least one s3 key/file should exist, e.g. '
                                   's3://bucket/prefix. The following values (with braces) will be substituted with '
                                   'the appropriate zero-padded values at runtime: {YEAR}, {MONTH}, {DAY}, {HOUR}, '
                                   '{MINUTE}, {SECOND}'
                },
                's3_path_regex': {
                    'type': ['string', 'null'],
                    'default': None,
                    'description': 'A regex pattern the s3 path must match. The following values (with braces) will '
                                   'be substituted with the appropriate zero-padded values at runtime: {YEAR}, {MONTH},'
                                   ' {DAY}, {HOUR}, {MINUTE}, {SECOND}'
                },
                'min_file_size_in_bytes': {
                    'type': ['integer', 'null'],
                    'default': 0,
                    'minimum': 0,
                    'description': 'If specified, at least one file matching the provided regex must be at least this size',
                },
                'date_offset_in_seconds': {
                    'type': ['integer', 'null'],
                    'default': 0,
                    'description': 'If specified, the date used in s3 path substitutions will be adjusted by this amount',
                },
                's3_file_last_modified': {
                    'type': ['boolean', 'null'],
                    'default': False,
                    'description': 'If specified, the data check factors last modified date into the data check',
                },
            },
            'additionalProperties': False,
            'required': ['s3_path_prefix'],
        },
    )
