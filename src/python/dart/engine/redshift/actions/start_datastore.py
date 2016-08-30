from dart.util.logging_utils import DartLogger
from dart.engine.redshift.admin.cluster import RedshiftCluster


_logger = DartLogger(__name__)


def start_datastore(redshift_engine, datastore, action):
    """
    :type redshift_engine: dart.engine.redshift.redshift.RedshiftEngine
    :type datastore: dart.model.datastore.Datastore
    :type action: dart.model.action.Action
    """
    cluster = RedshiftCluster(redshift_engine, datastore)
    cluster.start_or_resume(action.data.args.get('snapshot_name'))
    action = redshift_engine.dart.patch_action(action, progress=.1)
    cluster.wait_for_cluster_available()
    host, port, db = cluster.get_host_port_db()
    redshift_engine.dart.patch_action(action, progress=1)
    redshift_engine.dart.patch_datastore(
        datastore,
        host=host,
        port=port,
        connection_url='jdbc:redshift://%s:%s/%s' % (host, port, db)
    )
