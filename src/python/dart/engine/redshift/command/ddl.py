from dart.engine.redshift.mappings import mapped_column_definition
from dart.engine.redshift.metadata import RedshiftActionTypes


def get_target_schema_and_table_name(action, dataset):
    schema_name = action.data.args.get('target_schema_name') or 'public'
    table_name = action.data.args.get('target_table_name') or dataset.data.table_name
    return schema_name, table_name


def get_stage_schema_and_table_name(action, dataset):
    schema_name, table_name = get_target_schema_and_table_name(action, dataset)
    return 'dart_stage', schema_name + '_' + table_name + '_' + action.data.workflow_action_id


def get_tracking_schema_and_table_name(action):
    table_name = 's3_files_for_action_%s' % action.data.workflow_action_id
    if action.data.action_type_name == RedshiftActionTypes.consume_subscription.name:
        table_name = 's3_files_for_subscription_%s' % action.data.args['subscription_id']
    return 'dart_tracking', table_name


def create_tracking_schema_and_table(conn, action):
    schema_name, table_name = get_tracking_schema_and_table_name(action)
    conn.execute("CREATE SCHEMA IF NOT EXISTS %s" % schema_name)
    sql = "CREATE TABLE IF NOT EXISTS %s.%s (s3_path VARCHAR(1024), updated TIMESTAMP)" % (schema_name, table_name)
    if action.data.action_type_name == RedshiftActionTypes.consume_subscription.name:
        sql = "CREATE TABLE IF NOT EXISTS %s.%s (s3_path VARCHAR(1024), updated TIMESTAMP, batch_id VARCHAR(36))" % (schema_name, table_name)
    conn.execute(sql)


def create_schemas_and_tables(conn, action, dataset):
    """
    :type action: dart.model.action.Action
    :type dataset: dart.model.dataset.Dataset
    """
    args = action.data.args
    dd = dataset.data
    dist_key = args.get('target_distribution_key') or (dd.distribution_keys[0] if dd.distribution_keys else None)
    dist_style = 'KEY' if dist_key else (args.get('distribution_style') or 'EVEN')
    sk_keyword = 'INTERLEAVED SORTKEY' if args.get('sort_keys_interleaved') else 'SORTKEY'
    sort_keys = args.get('target_sort_keys') or dd.sort_keys
    schema_name, table_name = get_target_schema_and_table_name(action, dataset)

    table_sql = 'CREATE TABLE IF NOT EXISTS {schema_name}.{table_name}'
    table_options_sql = ' ({columns}{pk}){dist_style}{dist_key}{sort_keys}'.format(
        columns=', '.join([mapped_column_definition(c) for c in dataset.data.columns]),
        pk=', PRIMARY KEY (%s)' % ', '.join(dd.primary_keys) if dd.primary_keys else '',
        dist_style=' DISTSTYLE %s' % dist_style if dist_style else '',
        dist_key=' DISTKEY (%s)' % dist_key if dist_key else '',
        sort_keys=' %s (%s)' % (sk_keyword, ', '.join(sort_keys)) if sort_keys else '',
    )

    # create the schema and target table
    conn.execute("CREATE SCHEMA IF NOT EXISTS %s" % schema_name)
    sql = table_sql.format(schema_name=schema_name, table_name=table_name) + table_options_sql
    conn.execute(sql)

    # create the schema and stage table
    schema_name, table_name = get_stage_schema_and_table_name(action, dataset)
    conn.execute("CREATE SCHEMA IF NOT EXISTS %s" % schema_name)
    sql = table_sql.format(schema_name=schema_name, table_name=table_name) + table_options_sql
    conn.execute(sql)
