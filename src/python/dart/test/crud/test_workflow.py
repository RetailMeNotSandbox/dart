import unittest

from dart.client.python.dart_client import Dart
from dart.model.exception import DartRequestException
from dart.model.datastore import Datastore, DatastoreData, DatastoreState
from dart.model.workflow import Workflow, WorkflowData, WorkflowState


class TestWorkflowCrud(unittest.TestCase):
    def setUp(self):
        self.dart = Dart(host='localhost', port=5000)
        args = {'action_sleep_time_in_seconds': 0}
        dst = Datastore(data=DatastoreData(name='test-datastore',
                                           engine_name='no_op_engine',
                                           args=args,
                                           state=DatastoreState.ACTIVE))
        self.datastore = self.dart.save_datastore(dst)

    def tearDown(self):
        self.dart.delete_datastore(self.datastore.id)

    def test_crud(self):
        wf = Workflow(data=WorkflowData(name='test-workflow', datastore_id=self.datastore.id, engine_name='no_op_engine'))
        posted_wf = self.dart.save_workflow(wf, self.datastore.id)
        wf.data.user_id = posted_wf.data.user_id
        self.assertEqual(posted_wf.data.to_dict(), wf.data.to_dict())

        workflow = self.dart.get_workflow(posted_wf.id)
        self.assertEqual(posted_wf.to_dict(), workflow.to_dict())

        workflow.data.concurrency = 2
        workflow.data.state = WorkflowState.ACTIVE
        put_workflow = self.dart.save_workflow(workflow)
        self.assertEqual(put_workflow.data.concurrency, 2)
        self.assertEqual(put_workflow.data.state, WorkflowState.ACTIVE)
        self.assertNotEqual(posted_wf.to_dict(), put_workflow.to_dict())

        self.dart.delete_workflow(workflow.id)
        try:
            self.dart.get_workflow(workflow.id)
        except DartRequestException as e:
            self.assertEqual(e.response.status_code, 404)
            return

        self.fail('workflow should have been missing after delete!')


if __name__ == '__main__':
    unittest.main()
