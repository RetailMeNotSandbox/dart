from datetime import datetime
import logging

import boto3
from botocore.exceptions import ClientError, WaiterError
from retrying import retry
import sqlalchemy
from dart.model.datastore import Datastore

_logger = logging.getLogger(__name__)


def _retry_waiter_error(exception):
    if isinstance(exception, WaiterError):
        return True
    return False


class RedshiftCluster(object):
    def __init__(self, redshift_engine, datastore):
        self.redshift_engine = redshift_engine
        self.datastore = datastore
        self.master_user_name = self.datastore.data.args['master_user_name']
        self.master_db_name = self.datastore.data.args['master_db_name']
        self.snapshot_retention = self.datastore.data.args['snapshot_retention']
        self.cluster_identifier = datastore.data.args.get('cluster_identifier')
        if not self.cluster_identifier:
            self.cluster_identifier = 'dart-datastore-%s' % self.datastore.id

        assert isinstance(datastore, Datastore)
        # the presence of workflow_datastore_id indicates this datastore was created from a template in a workflow
        dsid = datastore.data.workflow_datastore_id or self.datastore.id
        self.password_key = 'dart-datastore-%s-master_user_password' % dsid

    def start_or_resume(self, snapshot_name=None):
        if self.cluster_exists():
            _logger.info("**** cluster %s: is already running" % self.cluster_identifier)
            return

        snapshot = self.get_snapshot_or_latest(snapshot_name)
        if snapshot:
            self.resume(snapshot['SnapshotIdentifier'])
            return

        self.start()

    def start(self):
        boto3.client('redshift').create_cluster(
            DBName=self.master_db_name,
            ClusterIdentifier=self.cluster_identifier,
            ClusterType='multi-node',
            NodeType=self.datastore.data.args['node_type'],
            MasterUsername=self.master_user_name,
            MasterUserPassword=self.get_master_password(),
            VpcSecurityGroupIds=self.redshift_engine.security_group_ids,
            ClusterSubnetGroupName=self.redshift_engine.vpc_subnet,
            AvailabilityZone=self.redshift_engine.random_availability_zone(),
            PreferredMaintenanceWindow=self.datastore.data.args['preferred_maintenance_window'],
            AutomatedSnapshotRetentionPeriod=0,
            AllowVersionUpgrade=False,
            NumberOfNodes=self.datastore.data.args['nodes'],
            PubliclyAccessible=self.redshift_engine.publicly_accessible,
            Encrypted=False,
            Tags=self.redshift_engine.cluster_tags,
        )

    def resume(self, snapshot_identifier):
        boto3.client('redshift').restore_from_cluster_snapshot(
            ClusterIdentifier=self.cluster_identifier,
            SnapshotIdentifier=snapshot_identifier,
            ClusterSubnetGroupName=self.redshift_engine.vpc_subnet,
            VpcSecurityGroupIds=self.redshift_engine.security_group_ids,
            AvailabilityZone=self.redshift_engine.random_availability_zone(),
            PubliclyAccessible=self.redshift_engine.publicly_accessible,
        )
        _logger.info("**** cluster %s restoring from snapshot %s", self.cluster_identifier, snapshot_identifier)

    def stop_cluster(self):
        """
        Stops an existing Redshift cluster and creates a final snapshot
        """
        if not self.cluster_exists():
            raise Exception('redshift cluster with identifier %s was not found' % self.cluster_identifier)

        _logger.info("Stopping cluster %s" % self.cluster_identifier)

        boto3.client('redshift').delete_cluster(
            ClusterIdentifier=self.cluster_identifier,
            SkipFinalClusterSnapshot=False,
            FinalClusterSnapshotIdentifier=self.cluster_identifier + '-' + datetime.utcnow().strftime("%Y%m%d%H%M%S")
        )
        self.purge_old_snapshots()

    def create_snapshot(self):
        snapshot_name = self.cluster_identifier + '-' + datetime.utcnow().strftime("%Y%m%d%H%M%S")
        boto3.client('redshift').create_cluster_snapshot(
            ClusterIdentifier=self.cluster_identifier,
            SnapshotIdentifier=snapshot_name,
        )
        return snapshot_name

    def purge_old_snapshots(self):
        snapshots_to_delete = self.get_snapshots_ordered_by_most_recent()[self.snapshot_retention:]
        for s in snapshots_to_delete:
            snapshot_name = s['SnapshotIdentifier']
            self.wait_for_snapshot_available(snapshot_name)
            boto3.client('redshift').delete_cluster_snapshot(
                SnapshotIdentifier=snapshot_name,
                SnapshotClusterIdentifier=self.cluster_identifier
            )

    def get_number_of_nodes(self):
        response = boto3.client('redshift').describe_clusters(ClusterIdentifier=self.cluster_identifier)
        return response['Clusters'][0]['NumberOfNodes']

    def get_host_port_db(self):
        cluster = self.describe_cluster()
        host = cluster['Endpoint']['Address']
        port = cluster['Endpoint']['Port']
        return host, port, self.master_db_name

    def get_master_password(self):
        return self.redshift_engine.secrets.get(self.password_key)

    def get_db_connection(self):
        self.wait_for_cluster_available()
        return self.get_db_engine().connect()

    @retry(wait_random_min=50000, wait_random_max=70000, stop_max_attempt_number=30, retry_on_exception=_retry_waiter_error)
    def wait_for_cluster_available(self):
        boto3.client('redshift').get_waiter('cluster_available').wait(ClusterIdentifier=self.cluster_identifier)

    @staticmethod
    @retry(wait_fixed=10000, stop_max_attempt_number=7, retry_on_exception=_retry_waiter_error)
    def wait_for_snapshot_available(snapshot_name):
        boto3.client('redshift').get_waiter('snapshot_available').wait(SnapshotIdentifier=snapshot_name)

    @retry(wait_fixed=10000, stop_max_attempt_number=7, retry_on_exception=_retry_waiter_error)
    def wait_for_cluster_deleted(self):
        boto3.client('redshift').get_waiter('cluster_deleted').wait(ClusterIdentifier=self.cluster_identifier)

    def get_db_engine(self):
        host, port, db = self.get_host_port_db()
        connection_string = 'redshift+psycopg2://{username}:{password}@{host}:{port}/{database}'.format(
            username=self.master_user_name, password=self.get_master_password(), host=host, port=port, database=db
        )
        return sqlalchemy.create_engine(connection_string)

    def get_snapshot_or_latest(self, snapshot_name):
        snapshots = self.get_snapshots_ordered_by_most_recent()
        if snapshot_name:
            for s in snapshots:
                if s['SnapshotIdentifier'] == snapshot_name:
                    return s
                raise Exception('unknown snapshot: %s' % snapshot_name)
        return snapshots[0] if snapshots else None

    def get_snapshots_ordered_by_most_recent(self):
        response = boto3.client('redshift').describe_cluster_snapshots(ClusterIdentifier=self.cluster_identifier)
        return sorted(response['Snapshots'], key=lambda x: x['SnapshotCreateTime'], reverse=True)

    def cluster_exists(self):
        try:
            self.describe_cluster()
            return True
        except ClientError as e:
            if e.response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 404:
                return False
            raise e

    def describe_cluster(self):
        response = boto3.client('redshift').describe_clusters(ClusterIdentifier=self.cluster_identifier)
        assert len(response['Clusters']) == 1, "expected describe_clusters response length to be 1"
        return response['Clusters'][0]
