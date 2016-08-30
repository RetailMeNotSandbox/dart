from dart.util.logging_utils import DartLogger

from dart.engine.redshift.admin.cluster import RedshiftCluster
from dart.engine.redshift.command.unload import unload_to_s3

_logger = DartLogger(__name__)


def copy_to_s3(redshift_engine, datastore, action):
    """
    :type redshift_engine: dart.engine.redshift.redshift.RedshiftEngine
    :type datastore: dart.model.datastore.Datastore
    :type action: dart.model.action.Action
    """
    cluster = RedshiftCluster(redshift_engine, datastore)
    conn = cluster.get_db_connection()
    txn = conn.begin()
    try:
        action = redshift_engine.dart.patch_action(action, progress=.1)
        unload_to_s3(action, conn)
        txn.commit()
        redshift_engine.dart.patch_action(action, progress=1)
    except:
        txn.rollback()
        raise
    finally:
        conn.close()
