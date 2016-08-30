from dart.util.logging_utils import DartLogger

from dart.engine.dynamodb.admin.table import DynamoDBTable
from dart.engine.dynamodb.mappings import mapped_column_type

_logger = DartLogger(__name__)


def create_table(dynamodb_engine, datastore, action):
    """
    :type dynamodb_engine: dart.engine.dynamodb.dynamodb.DynamoDBEngine
    :type datastore: dart.model.datastore.Datastore
    :type action: dart.model.action.Action
    """
    dataset = dynamodb_engine.dart.get_dataset(datastore.data.args['dataset_id'])
    table_name = datastore.data.args.get('target_table_name') or dataset.data.table_name
    dynamodb_table = DynamoDBTable(table_name)

    dynamodb_engine.dart.patch_action(action, progress=.1)
    hash_key_column = get_hash_key_column(datastore, dataset)
    sort_key_column = get_sort_key_column(datastore, dataset)

    key_schema = [{'AttributeName': hash_key_column.name, 'KeyType': 'HASH'}]
    attr_defs = [{'AttributeName': hash_key_column.name, 'AttributeType': mapped_column_type(hash_key_column)}]
    if sort_key_column:
        key_schema.append({'AttributeName': sort_key_column.name, 'KeyType': 'RANGE'})
        attr_defs.append({'AttributeName': sort_key_column.name, 'AttributeType': mapped_column_type(sort_key_column)})

    args = action.data.args
    dynamodb_table.create(attr_defs, key_schema, args['read_capacity_units'], args['write_capacity_units'])
    dynamodb_engine.dart.patch_action(action, progress=1)


def get_hash_key_column(datastore, dataset):
    name = datastore.data.args.get('target_distribution_key')
    if not name and not dataset.data.distribution_keys:
        raise Exception('dynamodb tables require a hash key, but none was available in the args or in the dataset')
    name = dataset.data.distribution_keys[0]
    matches = [c for c in dataset.data.columns if c.name == name]
    assert len(matches) == 1, 'there should have been one distribution_key with the name: %s' % name
    return matches[0]


def get_sort_key_column(datastore, dataset):
    name = datastore.data.args.get('target_sort_key')
    if not name and dataset.data.sort_keys:
        name = dataset.data.sort_keys[0]
    if name:
        matches = [c for c in dataset.data.columns if c.name == name]
        assert len(matches) == 1, 'there should have been one sort_key with the name: %s' % name
        return matches[0]
    return None
