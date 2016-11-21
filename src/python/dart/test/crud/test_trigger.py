import unittest

from dart.client.python.dart_client import Dart
from dart.model.exception import DartRequestException
from dart.model.datastore import Datastore, DatastoreData, DatastoreState
from dart.model.trigger import Trigger
from dart.model.trigger import TriggerData
from dart.model.workflow import WorkflowData, WorkflowState
from dart.model.workflow import Workflow


class TestTriggerCrud(unittest.TestCase):
    def setUp(self):
        self.dart = Dart(host='localhost', port=5000)
        args = {'action_sleep_time_in_seconds': 0}
        dst = Datastore(data=DatastoreData('test-datastore', 'no_op_engine', args=args, state=DatastoreState.TEMPLATE))
        self.datastore = self.dart.save_datastore(dst)
        wf = Workflow(data=WorkflowData('test-workflow', self.datastore.id, state=WorkflowState.ACTIVE))
        self.workflow = self.dart.save_workflow(wf, self.datastore.id)

    def tearDown(self):
        self.dart.delete_datastore(self.datastore.id)
        self.dart.delete_workflow(self.workflow.id)

    def test_crud(self):
        args = {'completed_workflow_id': self.workflow.id}
        tr = Trigger(data=TriggerData('test-trigger', 'workflow_completion', [self.workflow.id], args))
        posted_tr = self.dart.save_trigger(tr)
        tr.data.user_id = posted_tr.data.user_id

        # tags should get the wf_id so we remove it for the test sake
        posted_tr_data = posted_tr.data.to_dict()
        posted_tr_data['tags'] = []
        tr_data = tr.data.to_dict()
        tr_data['tags'] = []
        self.assertEqual(posted_tr_data, tr_data)

        trigger = self.dart.get_trigger(posted_tr.id)
        self.assertEqual(posted_tr.to_dict(), trigger.to_dict())

        self.dart.delete_trigger(trigger.id)
        try:
            self.dart.get_trigger(trigger.id)
        except DartRequestException as e:
            self.assertEqual(e.response.status_code, 404)
            return

        self.fail('trigger should have been missing after delete!')

if __name__ == '__main__':
    unittest.main()
