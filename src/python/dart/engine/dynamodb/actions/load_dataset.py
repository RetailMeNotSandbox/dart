from dart.util.logging_utils import DartLogger
import time
from dart.engine.dynamodb.admin.table import DynamoDBTable

from dart.engine.emr.actions.load_dataset import load_dataset_s3_path_and_file_size_generator, \
    prepare_load_dataset_steps
from dart.engine.emr.actions.start_datastore import prepare_bootstrap_actions, prepare_instance_groups, create_cluster

_logger = DartLogger(__name__)


def load_dataset(dynamodb_engine, datastore, action):
    """
    :type dynamodb_engine: dart.engine.dynamodb.dynamodb.DynamoDBEngine
    :type datastore: dart.model.datastore.Datastore
    :type action: dart.model.action.Action
    """
    emr = dynamodb_engine.emr_engine
    dataset = dynamodb_engine.dart.get_dataset(datastore.data.args['dataset_id'])
    table_name = datastore.data.args.get('target_table_name') or dataset.data.table_name
    dynamodb_table = DynamoDBTable(table_name)
    generator = load_dataset_s3_path_and_file_size_generator(emr, action, dataset)
    for_dynamodb = True
    data_to_freespace_ratio = 0.5

    if action.data.args.get('initial_write_capacity_units'):
        dynamodb_table.set_write_capacity_units(action.data.args['initial_write_capacity_units'])
        dynamodb_engine.dart.patch_action(action, progress=.1)

    action.data.args['dataset_id'] = dataset.id
    action.data.args['target_table_name'] = table_name
    cluster_name = 'dart-datastore-%s-%s-dynamodb' % (datastore.id, datastore.data.name)
    instance_groups = prepare_instance_groups(emr, datastore, [action], emr.core_node_limit, data_to_freespace_ratio)
    bootstrap_actions = prepare_bootstrap_actions(datastore, emr.impala_docker_repo_base_url, emr.impala_version)
    steps = [wrapper.step for wrapper in prepare_load_dataset_steps(False, action.data.args, datastore, dataset, action.id, generator, for_dynamodb)]
    for step in steps:
        step.action_on_failure = 'TERMINATE_CLUSTER'

    datastore.data.args['release_label'] = dynamodb_engine.emr_release_label
    datastore.data.args['instance_type'] = dynamodb_engine.emr_instance_type
    auto_terminate = True
    cluster_id = create_cluster(bootstrap_actions, cluster_name, datastore, emr, instance_groups, steps, auto_terminate)
    dynamodb_engine.dart.patch_action(action, progress=.2)

    exception = None
    while True:
        state = emr.conn.describe_cluster(cluster_id).status.state
        # http://docs.aws.amazon.com/ElasticMapReduce/latest/DeveloperGuide/ProcessingCycle.html
        # using cluster state since describe_jobflow is deprecated
        # https://aws.amazon.com/elasticmapreduce/faqs/
        if state == 'TERMINATED':
            break
        if state in ['TERMINATED_WITH_ERRORS']:
            exception = Exception('the underlying EMR job failed (cluster_id=%s)' % cluster_id)
            break
        time.sleep(30)

    if action.data.args.get('final_write_capacity_units'):
        dynamodb_table.set_write_capacity_units(action.data.args['final_write_capacity_units'])
        dynamodb_engine.dart.patch_action(action, progress=.9)

    if exception:
        raise exception

    dynamodb_engine.dart.patch_action(action, progress=1)
