from itertools import islice
from dart.util.strings import substitute_date_tokens
from datetime import datetime
import json
import logging
import os
import tempfile
import boto3

from dart.engine.redshift.admin.utils import lookup_credentials
from dart.engine.redshift.command.ddl import get_target_schema_and_table_name, get_stage_schema_and_table_name, \
    get_tracking_schema_and_table_name
from dart.model.dataset import RowFormat, Compression, LoadType
from dart.util.s3 import get_bucket_name, get_key_name

core_counts_by_instance_type = {
    'ds1.xlarge': 2,
    'ds1.8xlarge': 16,
    'ds2.xlarge': 4,
    'ds2.8xlarge': 36,
    'dc1.large': 2,
    'dc1.8xlarge': 32,
}

_logger = logging.getLogger(__name__)


def copy_from_s3(dart, datastore, action, dataset, conn, batch_size, s3_path_and_updated_generator):
    """
    :type dart: dart.client.python.dart_client.Dart
    :type datastore: dart.model.datastore.Datastore
    :type action: dart.model.action.Action
    :type dataset: dart.model.dataset.Dataset
    """
    _logger.info('starting copy_from_s3')
    if dataset.data.load_type == LoadType.MERGE:
        assert dataset.data.merge_keys, 'load_type was MERGE, but merge_keys is empty!'

    safe_batch_size = batch_size
    if dataset.data.load_type == LoadType.MERGE and not dataset.data.batch_merge_sort_keys:
        safe_batch_size = 1
    elif action.data.args.get('batch_size'):
        # allow overrides
        safe_batch_size = action.data.args['batch_size']

    _logger.info('getting manifests and tracking_sql_files')
    manifests, tracking_sql_files = \
        _upload_s3_copy_manifests_and_create_tracking_sql_files(action, dataset, datastore, safe_batch_size,
                                                                s3_path_and_updated_generator)
    stage_schema_name, stage_table_name = get_stage_schema_and_table_name(action, dataset)
    target_schema_name, target_table_name = get_target_schema_and_table_name(action, dataset)
    steps_total = len(manifests) + (5 if dataset.data.load_type == LoadType.MERGE else 4)
    step_num = 1

    # truncate the stage table
    conn.execute("TRUNCATE TABLE %s.%s" % (stage_schema_name, stage_table_name))
    action = dart.patch_action(action, progress=_get_progress(step_num, steps_total))

    # load the stage table
    action, step_num = _load_stage_table(
        action, conn, dart, dataset, datastore, manifests, stage_schema_name, stage_table_name, step_num, steps_total
    )
    # truncate the target table if this is a reload
    if dataset.data.load_type in [LoadType.RELOAD_ALL, LoadType.RELOAD_LAST]:
        conn.execute("TRUNCATE TABLE %s.%s" % (target_schema_name, target_table_name))

    # move the data from the stage table to the target table and update the tracking table within one transaction
    txn = conn.begin()
    try:
        action, step_num = _load_target_table(action, conn, dart, dataset, stage_schema_name, stage_table_name,
                                              step_num, steps_total, target_schema_name, target_table_name)

        for tracking_sql_file in tracking_sql_files:
            with open(tracking_sql_file) as f:
                conn.execute(f.read())
            os.remove(tracking_sql_file)
        step_num += 1
        action = dart.patch_action(action, progress=_get_progress(step_num, steps_total))

        txn.commit()
    except:
        txn.rollback()
        raise

    # drop the stage table
    conn.execute("DROP TABLE %s.%s" % (stage_schema_name, stage_table_name))
    dart.patch_action(action, progress=1)


def _load_target_table(action, conn, dart, dataset, stage_schema_name, stage_table_name, step_num, steps_total,
                       target_schema_name, target_table_name):
    if dataset.data.load_type == LoadType.MERGE:
        sql = 'DELETE FROM {target_schema_name}.{target_table_name} ' \
              'WHERE ({merge_keys}) IN (SELECT DISTINCT {merge_keys} FROM {stage_schema_name}.{stage_table_name})'
        sql = sql.format(
            stage_schema_name=stage_schema_name,
            stage_table_name=stage_table_name,
            target_schema_name=target_schema_name,
            target_table_name=target_table_name,
            merge_keys=', '.join(dataset.data.merge_keys),
        )
        conn.execute(sql)
        step_num += 1
        action = dart.patch_action(action, progress=_get_progress(step_num, steps_total))

    if dataset.data.load_type == LoadType.MERGE and dataset.data.batch_merge_sort_keys:
        sql = """
            INSERT INTO {target_schema_name}.{target_table_name} ({columns})
            SELECT DISTINCT {columns}
            FROM (
              SELECT {columns}, rank() OVER (PARTITION BY {merge_keys} ORDER BY {batch_merge_sort_keys}) AS ranking
              FROM {stage_schema_name}.{stage_table_name}
            ) t
            WHERE ranking = 1;
        """
        sql = sql.format(
            stage_schema_name=stage_schema_name,
            stage_table_name=stage_table_name,
            target_schema_name=target_schema_name,
            target_table_name=target_table_name,
            columns=', '.join([c.name for c in dataset.data.columns]),
            merge_keys=', '.join(dataset.data.merge_keys),
            batch_merge_sort_keys=', '.join(dataset.data.batch_merge_sort_keys),
        )
        conn.execute(sql)
        step_num += 1
        action = dart.patch_action(action, progress=_get_progress(step_num, steps_total))

    else:
        sql = "INSERT INTO {target_schema_name}.{target_table_name} " \
              "SELECT * FROM {stage_schema_name}.{stage_table_name}"
        sql = sql.format(
            stage_schema_name=stage_schema_name,
            stage_table_name=stage_table_name,
            target_schema_name=target_schema_name,
            target_table_name=target_table_name,
        )
        conn.execute(sql)
        step_num += 1
        action = dart.patch_action(action, progress=_get_progress(step_num, steps_total))

    return action, step_num


def _load_stage_table(action, conn, dart, dataset, datastore, manifests, stage_schema_name, stage_table_name,
                      step_num, steps_total):
    for step_num, s3_manifest_path in enumerate(manifests, start=2):
        aws_access_key_id, aws_secret_access_key, security_token = lookup_credentials(action)
        sql = _get_copy_from_s3_sql(datastore, action, dataset, stage_schema_name, stage_table_name,
                                    s3_manifest_path, aws_access_key_id, aws_secret_access_key, security_token)
        try:
            conn.execute(sql)
        except Exception as e:
            if "Check 'stl_load_errors' system table for details" in e.message:
                now = datetime.utcnow()
                filename = substitute_date_tokens(dataset.data.location, now)
                stl_load_error_sql = "SELECT * FROM pg_catalog.stl_load_errors WHERE filename LIKE '{filename}%%' " \
                                     "ORDER BY starttime DESC LIMIT 1".format(filename=filename)
                stl_load_error = conn.execute(stl_load_error_sql).fetchone()
                exception_message = "Load into {table_name} failed.\n" \
                                    "stl_load_error:\n" \
                                    "Start Time: {starttime}\n" \
                                    "Filename: {filename}\n" \
                                    "Line No.: {line_number}\n" \
                                    "Column Name: {colname}\n" \
                                    "Type: {type}\n" \
                                    "Column Length: {col_length}\n" \
                                    "Position: {position}\n" \
                                    "Raw Line: {raw_line}\n" \
                                    "Raw Field Value: {raw_field_value}\n" \
                                    "Error Code: {err_code}\n" \
                                    "Error Reason: {err_reason}"
                exception_message = exception_message.format(
                    table_name=stage_table_name,
                    starttime=stl_load_error['starttime'],
                    filename=stl_load_error['filename'],
                    line_number=stl_load_error['line_number'],
                    colname=stl_load_error['colname'],
                    type=stl_load_error['type'],
                    col_length=stl_load_error['col_length'],
                    position=stl_load_error['position'],
                    raw_line=stl_load_error['raw_line'],
                    raw_field_value=stl_load_error['raw_field_value'],
                    err_code=stl_load_error['err_code'],
                    err_reason=stl_load_error['err_reason']
                )
                raise Exception(exception_message)
            else:
                raise e
        action = dart.patch_action(action, progress=_get_progress(step_num, steps_total))

    return action, step_num + 1


def _get_progress(step_num, steps_total):
    return "%.2f" % round(float(step_num) / float(steps_total), 2)


def _upload_s3_copy_manifests_and_create_tracking_sql_files(action, dataset, datastore, batch_size,
                                                            s3_path_and_updated_generator):
    """
    :type action: dart.model.action.Action
    :type dataset: dart.model.dataset.Dataset
    :type datastore: dart.model.datastore.Datastore
    """
    s3_path_and_updated_iterator = iter(s3_path_and_updated_generator)

    if dataset.data.load_type == LoadType.RELOAD_LAST:
        last = None
        for last in s3_path_and_updated_iterator:
            pass
        s3_path_and_updated_iterator = iter([last] if last else [])

    manifests = []
    tracking_sql_files = []
    current_part = 1
    while True:
        batch = list(islice(s3_path_and_updated_iterator, batch_size))
        if not batch:
            break

        with tempfile.NamedTemporaryFile() as f:
            values = (datastore.data.s3_artifacts_path, action.id, current_part)
            s3_manifest_path = '%s/load-manifests/load-manifest-for-action-%s-part-%s.json' % values
            manifests.append(s3_manifest_path)
            # http://docs.aws.amazon.com/redshift/latest/dg/loading-data-files-using-manifest.html
            data = {'entries': [{'mandatory': True, 'url': e[0]} for e in batch]}
            json.dump(data, f)
            # now rewind to the beginning of the file so it can be read
            f.seek(0)
            bucket_name = get_bucket_name(datastore.data.s3_artifacts_path)
            key_name = get_key_name(s3_manifest_path)
            boto3.client('s3').upload_file(f.name, bucket_name, key_name)

        with tempfile.NamedTemporaryFile(delete=False) as f:
            tracking_sql_files.append(f.name)
            schema_name, table_name = get_tracking_schema_and_table_name(action)
            sql = 'INSERT INTO %s.%s (s3_path, updated) VALUES \n' % (schema_name, table_name)
            sql += ',\n'.join(["('%s', %s)" % (e[0], "'%s'" % e[1].isoformat() if e[1] else 'NULL') for e in batch])
            f.write(sql)

        current_part += 1
    return manifests, tracking_sql_files


def _get_copy_from_s3_sql(datastore, action, dataset, schema_name, table_name, s3_manifest_path, aws_access_key_id,
                          aws_secret_access_key, security_token):
    """
    :type datastore: dart.model.datastore.Datastore
    :type action: dart.model.action.Action
    :type dataset: dart.model.dataset.Dataset
    :type table_name: str
    :type s3_manifest_path: str
    """
    options = []
    df = dataset.data.data_format

    if df.row_format == RowFormat.JSON:
        s3_json_manifest_path = _upload_s3_json_manifest(action, dataset, datastore)
        options.append("FORMAT AS JSON '%s'" % s3_json_manifest_path)
    elif df.row_format == RowFormat.DELIMITED:
        options.append("NULL AS '%s'" % df.null_string)
        options.append("DELIMITER '%s'" % df.delimited_by)
        options.append("IGNOREHEADER %s" % df.num_header_rows)
        options.append('REMOVEQUOTES') if df.quoted_by in ['"', "'"] else None
        options.append('FILLRECORD')
        options.append('IGNOREBLANKLINES')
        options.append('ESCAPE') if dataset.data.data_format.escaped_by == '\\' else None
    else:
        raise Exception('unsupported row format: %s' % df.row_format)

    if dataset.data.compression == Compression.NONE:
        pass
    elif dataset.data.compression == Compression.BZ2:
        options.append('BZIP2')
    elif dataset.data.compression == Compression.GZIP:
        options.append('GZIP')
    else:
        raise Exception('unsupported compression type: %s' % dataset.data.compression)

    options.append('TRUNCATECOLUMNS') if action.data.args.get('truncate_columns', False) else None
    options.append('MANIFEST')

    sql = "COPY {schema_name}.{table_name} FROM '{s3_manifest_path}' {options} MAXERROR {max_error}" \
          " DATEFORMAT 'auto'" \
          " TIMEFORMAT 'auto'" \
          " CREDENTIALS 'aws_access_key_id={aws_access_key_id};aws_secret_access_key={aws_secret_access_key}{token}'"
    return sql.format(
        schema_name=schema_name,
        table_name=table_name,
        s3_manifest_path=s3_manifest_path,
        options=' '.join(options),
        max_error=action.data.args.get('max_errors', 0),
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        token=';token=%s' % security_token if security_token else ''
    )


def _upload_s3_json_manifest(action, dataset, datastore):
    # http://docs.aws.amazon.com/redshift/latest/dg/copy-usage_notes-copy-from-json.html
    data = {'jsonpaths': ['$.%s' % c.path for c in dataset.data.columns]}
    values = (datastore.data.s3_artifacts_path, action.id)
    s3_json_manifest_path = '%s/json-manifests/json-manifest-for-action-%s.json' % values
    with tempfile.NamedTemporaryFile() as f:
        json.dump(data, f)
        # now rewind to the beginning of the file so it can be read
        f.seek(0)
        bucket_name = get_bucket_name(datastore.data.s3_artifacts_path)
        key_name = get_key_name(s3_json_manifest_path)
        boto3.client('s3').upload_file(f.name, bucket_name, key_name)
    return s3_json_manifest_path
