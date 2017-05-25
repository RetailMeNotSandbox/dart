from datetime import datetime
import re
from retrying import retry
from dart.util.shell import call
from dart.util.strings import substitute_date_tokens


def get_bucket(conn, s3_path):
    assert s3_path.startswith('s3://')
    return conn.get_bucket(get_bucket_name(s3_path))


def get_s3_path(key_object):
    return 's3://' + key_object.bucket.name + '/' + key_object.key


def yield_s3_keys(bucket, s3_path_root_prefix, s3_path_start_prefix_inclusive=None, s3_path_end_prefix_exclusive=None,
                  s3_path_regex_filter=None, s3_path_start_prefix_inclusive_date_offset_in_seconds=0,
                  s3_path_end_prefix_exclusive_date_offset_in_seconds=0, s3_path_regex_filter_date_offset_in_seconds=0):

    now = datetime.utcnow()
    s3_path_start_prefix_inclusive = substitute_date_tokens(s3_path_start_prefix_inclusive, now, s3_path_start_prefix_inclusive_date_offset_in_seconds)
    s3_path_end_prefix_exclusive = substitute_date_tokens(s3_path_end_prefix_exclusive, now, s3_path_end_prefix_exclusive_date_offset_in_seconds)
    s3_path_regex_filter = substitute_date_tokens(s3_path_regex_filter, now, s3_path_regex_filter_date_offset_in_seconds)

    marker = ''
    for key_obj in bucket.list(prefix=get_key_name(s3_path_start_prefix_inclusive or s3_path_root_prefix),
                               marker=marker):
        s3_path = get_s3_path(key_obj)
        if s3_path.rstrip('/') == s3_path_root_prefix.rstrip('/'):
            continue
        if s3_path_start_prefix_inclusive and s3_path < s3_path_start_prefix_inclusive:
            continue
        if s3_path_end_prefix_exclusive and s3_path >= s3_path_end_prefix_exclusive:
            return
        if s3_path_regex_filter and not re.search(s3_path_regex_filter, s3_path):
            continue
        yield key_obj


def get_bucket_name(s3_path):
    return s3_path.split('s3://', 1)[1].split('/', 1)[0]


def get_key_name(s3_path):
    if not s3_path.startswith('s3://'):
        return s3_path
    return s3_path.split('s3://', 1)[1].split('/', 1)[1]


# we experience occasional S3 API issues, so we will retry a few times
@retry(wait_fixed=10000, stop_max_attempt_number=12)
def s3_copy_recursive(source_path, dest_path):
    call('aws s3 cp --recursive %s %s' % (source_path, dest_path))
