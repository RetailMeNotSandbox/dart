from datetime import datetime, timedelta
import logging
import re

import boto3

from dart.util.s3 import get_bucket_name, get_key_name
from dart.util.strings import substitute_date_tokens

_logger = logging.getLogger(__name__)


def data_check(s3_engine, datastore, action):
    """
    :type s3_engine: dart.engine.s3.s3.S3Engine
    :type datastore: dart.model.datastore.Datastore
    :type action: dart.model.action.Action
    """
    action = s3_engine.dart.patch_action(action, progress=.1)
    args = action.data.args
    offset = args.get('date_offset_in_seconds')
    now = datetime.utcnow()
    s3_path_prefix = substitute_date_tokens(args['s3_path_prefix'], now, offset)
    bucket_name = get_bucket_name(s3_path_prefix)
    prefix = get_key_name(s3_path_prefix)
    last_modified = args.get('s3_file_last_modified')

    s3_paginator = boto3.client('s3').get_paginator('list_objects')
    for page in s3_paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        for element in (page.get('Contents') or []):
            path = 's3://' + bucket_name + '/' + element['Key']
            s3_path_regex = args.get('s3_path_regex')
            if s3_path_regex and not re.match(substitute_date_tokens(s3_path_regex, now, offset), path):
                continue
            if args.get('min_file_size_in_bytes') and element['Size'] < args['min_file_size_in_bytes']:
                continue
            if last_modified and element['LastModified'] < now + timedelta(seconds=offset):
                continue
            return

    raise Exception('Data check failed')
