from dart.util.logging_utils import DartLogger
import boto

from dart.engine.redshift.admin.cluster import RedshiftCluster
from dart.engine.redshift.command.copy import copy_from_s3, core_counts_by_instance_type
from dart.engine.redshift.command.ddl import create_schemas_and_tables, create_tracking_schema_and_table
from dart.util.s3 import get_s3_path, yield_s3_keys, get_bucket

_logger = DartLogger(__name__)


def load_dataset(redshift_engine, datastore, action):
    """
    :type redshift_engine: dart.engine.redshift.redshift.RedshiftEngine
    :type datastore: dart.model.datastore.Datastore
    :type action: dart.model.action.Action
    """
    dataset = redshift_engine.dart.get_dataset(action.data.args['dataset_id'])
    cluster = RedshiftCluster(redshift_engine, datastore)
    batch_size = cluster.get_number_of_nodes() * core_counts_by_instance_type.get(datastore.data.args['node_type'])
    conn = cluster.get_db_connection()

    try:
        create_schemas_and_tables(conn, action, dataset)
        create_tracking_schema_and_table(conn, action)

        s3_path_and_updated_generator = _s3_path_and_updated_generator(action, dataset)
        copy_from_s3(redshift_engine.dart, datastore, action, dataset, conn, batch_size, s3_path_and_updated_generator)
    finally:
        conn.close()


def _s3_path_and_updated_generator(action, dataset):
    conn = boto.connect_s3()
    s3_keys = yield_s3_keys(
        get_bucket(conn, dataset.data.location),
        dataset.data.location,
        action.data.args.get('s3_path_start_prefix_inclusive'),
        action.data.args.get('s3_path_end_prefix_exclusive'),
        action.data.args.get('s3_path_regex_filter'),
        action.data.args.get('s3_path_start_prefix_inclusive_date_offset_in_seconds'),
        action.data.args.get('s3_path_end_prefix_exclusive_date_offset_in_seconds'),
        action.data.args.get('s3_path_regex_filter_date_offset_in_seconds'),
    )
    for key_obj in s3_keys:
        yield get_s3_path(key_obj), None
