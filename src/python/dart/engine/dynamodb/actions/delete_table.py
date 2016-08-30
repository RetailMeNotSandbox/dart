from dart.util.logging_utils import DartLogger
from dart.engine.dynamodb.admin.table import DynamoDBTable

_logger = DartLogger(__name__)


def delete_table(dynamodb_engine, datastore, action):
    """
    :type dynamodb_engine: dart.engine.dynamodb.dynamodb.DynamoDBEngine
    :type datastore: dart.model.datastore.Datastore
    :type action: dart.model.action.Action
    """
    dataset = dynamodb_engine.dart.get_dataset(datastore.data.args['dataset_id'])
    table_name = datastore.data.args.get('target_table_name') or dataset.data.table_name
    dynamodb_engine.dart.patch_action(action, progress=.1)
    DynamoDBTable(table_name).delete()
    dynamodb_engine.dart.patch_action(action, progress=1)
