from dart.util.logging_utils import DartLogger

from dart.engine.redshift.admin.cluster import RedshiftCluster
from dart.engine.redshift.admin.utils import sanitized_query

_logger = DartLogger(__name__)


def data_check(redshift_engine, datastore, action):
    """
    :type redshift_engine: dart.engine.redshift.redshift.RedshiftEngine
    :type datastore: dart.model.datastore.Datastore
    :type action: dart.model.action.Action
    """
    cluster = RedshiftCluster(redshift_engine, datastore)
    conn = cluster.get_db_connection()
    try:
        action = redshift_engine.dart.patch_action(action, progress=.1)
        result = list(conn.execute(sanitized_query(action.data.args['sql_script'])))[0][0]
        if result:
            redshift_engine.dart.patch_action(action, progress=1)
        else:
            raise Exception('Data check failed')
    finally:
        conn.close()
