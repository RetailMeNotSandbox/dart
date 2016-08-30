from dart.util.logging_utils import DartLogger
import boto3

from dart.util.s3 import get_bucket_name, get_key_name

_logger = DartLogger(__name__)


def copy(s3_engine, datastore, action):
    """
    :type s3_engine: dart.engine.s3.s3.S3Engine
    :type datastore: dart.model.datastore.Datastore
    :type action: dart.model.action.Action
    """
    return s3_copy(**action.data.args)


def extract_bucket_key(s3_path):
    return get_bucket_name(s3_path), get_key_name(s3_path)


def perform_s3_copy_recursive(s3_client, from_path, to_path):
    from_bucket, from_key_path = extract_bucket_key(from_path)
    to_bucket, to_key_path = extract_bucket_key(to_path)
    s3_paginator = s3_client.get_paginator('list_objects')
    for page in s3_paginator.paginate(Bucket=from_bucket, Prefix=from_key_path):
        if page.get('Contents'):
            for key in page.get('Contents'):
                # Extract filename relative to the from_path
                base_filename = key.get('Key').replace(from_key_path, '')
                if base_filename:
                    _logger.info('Copying key %s to destination %s' % (
                        from_key_path + base_filename, to_key_path + base_filename))
                    copy_s3_object(s3_client, from_bucket, from_key_path + base_filename, to_bucket,
                                   to_key_path + base_filename)


def perform_s3_copy(s3_client, from_path, to_path):
    from_bucket, from_key_path = extract_bucket_key(from_path)
    to_bucket, to_key_path = extract_bucket_key(to_path)
    _logger.info('Copying key %s to destination %s' % (from_path, to_path))
    copy_s3_object(s3_client, from_bucket, from_key_path, to_bucket, to_key_path)


def copy_s3_object(s3_client, from_bucket, from_key_path, to_bucket, to_key_path):
    try:
        s3_client.copy_object(
            ACL='bucket-owner-full-control',
            Bucket=to_bucket,
            Key=to_key_path,
            CopySource={'Bucket': from_bucket, 'Key': from_key_path},
        )
    except Exception as e:
        raise e


def s3_copy(from_path, to_path, recursive):
    """
    Performs s3 to s3 copy. Recursive flag performs recursive copy
    :param from_path:
     :type from_path: str
    :param to_path:
     :type to_path: str
    :param recursive:
     :type recursive: boolean
    :return:
    """
    client = boto3.client('s3')
    if recursive:
        perform_s3_copy_recursive(client, from_path, to_path)
    else:
        perform_s3_copy(client, from_path, to_path)
