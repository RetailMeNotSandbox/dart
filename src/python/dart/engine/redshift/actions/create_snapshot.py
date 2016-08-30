from dart.util.logging_utils import DartLogger
from dart.engine.redshift.admin.cluster import RedshiftCluster

_logger = DartLogger(__name__)


def create_snapshot(redshift_engine, datastore, action):
    """
    :type redshift_engine: dart.engine.redshift.redshift.RedshiftEngine
    :type datastore: dart.model.datastore.Datastore
    :type action: dart.model.action.Action
    """
    cluster = RedshiftCluster(redshift_engine, datastore)
    snapshot_name = cluster.create_snapshot()
    action = redshift_engine.dart.patch_action(action, progress=.1)
    cluster.wait_for_snapshot_available(snapshot_name)
    cluster.purge_old_snapshots()
    redshift_engine.dart.patch_action(action, progress=1)
