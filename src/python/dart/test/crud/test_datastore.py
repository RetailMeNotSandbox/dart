import unittest

from dart.client.python.dart_client import Dart
from dart.model.exception import DartRequestException
from dart.model.datastore import Datastore, DatastoreData, DatastoreState


class TestDatastoreCrud(unittest.TestCase):
    def setUp(self):
        self.dart = Dart(host='localhost', port=5000)

    def test_crud(self):
        dst = Datastore(data=DatastoreData(
            name='test-datastore',
            engine_name='no_op_engine',
            args={'action_sleep_time_in_seconds': 0},
            tags=['foo']
        ))
        posted_datastore = self.dart.save_datastore(dst)

        # copy fields that are populated at creation time
        dst.data.s3_artifacts_path = posted_datastore.data.s3_artifacts_path
        dst.data.s3_logs_path = posted_datastore.data.s3_logs_path
        dst.data.user_id = posted_datastore.data.user_id
        self.assertEqual(posted_datastore.data.to_dict(), dst.data.to_dict())

        datastore = self.dart.get_datastore(posted_datastore.id)
        self.assertEqual(posted_datastore.to_dict(), datastore.to_dict())

        datastore.data.engine_name = 'not_existing_engine'
        datastore.data.state = DatastoreState.ACTIVE
        put_datastore = self.dart.save_datastore(datastore)
        # not all properties can be modified
        self.assertEqual(put_datastore.data.engine_name, 'no_op_engine')
        self.assertEqual(put_datastore.data.state, DatastoreState.ACTIVE)
        self.assertNotEqual(posted_datastore.to_dict(), put_datastore.to_dict())

        self.dart.delete_datastore(datastore.id)
        try:
            self.dart.get_datastore(datastore.id)
        except DartRequestException as e:
            self.assertEqual(e.response.status_code, 404)
            return

        self.fail('datastore should have been missing after delete!')


if __name__ == '__main__':
    unittest.main()
