from dart.util.logging_utils import DartLogger
from dart.engine.redshift.admin.cluster import RedshiftCluster

_logger = DartLogger(__name__)


def stop_datastore(redshift_engine, datastore, action):
    """
    :type redshift_engine: dart.engine.redshift.redshift.RedshiftEngine
    :type datastore: dart.model.datastore.Datastore
    :type action: dart.model.action.Action
    """
    cluster = RedshiftCluster(redshift_engine, datastore)
    cluster.stop_cluster()
    action = redshift_engine.dart.patch_action(action, progress=.1)
    cluster.wait_for_cluster_deleted()
    redshift_engine.dart.patch_action(action, progress=1)
