from dart.model.datastore import DatastoreState
from dart.model.exception import DartUserError


def terminate_datastore(emr_engine, datastore, action):
    """
    :type emr_engine: dart.engine.emr.emr.EmrEngine
    :type datastore: dart.model.datastore.Datastore
    :type action: dart.model.action.Action
    """
    if datastore.data.args['dry_run']:
        emr_engine.dart.patch_action(action, progress=1)
        return

    extra_data = datastore.data.extra_data or {}
    cluster_id = extra_data.get('cluster_id')
    if not cluster_id:
        raise DartUserError('Cannot terminate datastore before starting')

    emr_engine.conn.terminate_jobflow(cluster_id)
    emr_engine.dart.patch_datastore(datastore, state=DatastoreState.DONE)
    emr_engine.dart.patch_action(action, progress=1)
