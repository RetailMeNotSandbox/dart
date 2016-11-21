import unittest

from dart.client.python.dart_client import Dart
from dart.engine.no_op.metadata import NoOpActionTypes
from dart.model.exception import DartRequestException
from dart.model.action import Action, ActionData, ActionState
from dart.model.datastore import Datastore, DatastoreData, DatastoreState
from dart.model.workflow import Workflow, WorkflowData


class TestActionCrud(unittest.TestCase):
    def setUp(self):
        self.dart = Dart(host='localhost', port=5000)
        args = {'action_sleep_time_in_seconds': 0}
        dst = Datastore(data=DatastoreData(name='test-datastore', engine_name='no_op_engine', args=args, state=DatastoreState.TEMPLATE))
        self.datastore = self.dart.save_datastore(dst)
        wf = Workflow(data=WorkflowData(name='test-workflow', datastore_id=self.datastore.id))
        self.workflow = self.dart.save_workflow(workflow=wf, datastore_id=self.datastore.id)
        self.maxDiff = 99999

    def tearDown(self):
        self.dart.delete_datastore(self.datastore.id)
        self.dart.delete_workflow(self.workflow.id)

    def test_crud_datastore(self):
        action0 = Action(data=ActionData(name=NoOpActionTypes.action_that_succeeds.name,
                                         action_type_name=NoOpActionTypes.action_that_succeeds.name,
                                         engine_name='no_op_engine'))
        action1 = Action(data=ActionData(name=NoOpActionTypes.action_that_succeeds.name,
                                         action_type_name=NoOpActionTypes.action_that_succeeds.name,
                                         engine_name='no_op_engine'))
        posted_actions = self.dart.save_actions(actions=[action0, action1], datastore_id=self.datastore.id)

        # copy fields that are populated at creation time
        action0.data.datastore_id = posted_actions[0].data.datastore_id
        action1.data.datastore_id = posted_actions[1].data.datastore_id
        action0.data.args = {}
        action1.data.args = {}
        action0.data.order_idx = posted_actions[0].data.order_idx
        action1.data.order_idx = posted_actions[1].data.order_idx

        action0.data.user_id = posted_actions[0].data.user_id
        action1.data.user_id = posted_actions[1].data.user_id

        self.assertEqual(posted_actions[0].data.to_dict(), action0.data.to_dict())
        self.assertEqual(posted_actions[1].data.to_dict(), action1.data.to_dict())

        # When retrieving an action, its queue time and state
        # differs from the action default values created by action0 and action1
        a0 = self.dart.get_action(posted_actions[0].id)
        a1 = self.dart.get_action(posted_actions[1].id)
        action0.data.state = a0.data.state
        action1.data.state = a1.data.state
        action0.data.queued_time = a0.data.queued_time
        action1.data.queued_time = a1.data.queued_time

        self.assertEqual(a0.data.to_dict(), action0.data.to_dict())
        self.assertEqual(a1.data.to_dict(), action1.data.to_dict())

        self.dart.delete_action(a0.id)
        self.dart.delete_action(a1.id)

        try:
            self.dart.get_action(a0.id)
        except DartRequestException as e0:
            self.assertEqual(e0.response.status_code, 404)
            try:
                self.dart.get_action(a1.id)
            except DartRequestException as e1:
                self.assertEqual(e1.response.status_code, 404)
                return

        self.fail('action should have been missing after delete!')

    def test_crud_workflow(self):
        action0 = Action(data=ActionData(name=NoOpActionTypes.action_that_succeeds.name, action_type_name=NoOpActionTypes.action_that_succeeds.name, state=ActionState.TEMPLATE, engine_name='no_op_engine'))
        action1 = Action(data=ActionData(name=NoOpActionTypes.action_that_succeeds.name, action_type_name=NoOpActionTypes.action_that_succeeds.name, state=ActionState.TEMPLATE, engine_name='no_op_engine'))
        posted_actions = self.dart.save_actions([action0, action1], workflow_id=self.workflow.id)

        # copy fields that are populated at creation time
        action0.data.workflow_id = posted_actions[0].data.workflow_id
        action1.data.workflow_id = posted_actions[1].data.workflow_id
        action0.data.order_idx = posted_actions[0].data.order_idx
        action1.data.order_idx = posted_actions[1].data.order_idx
        action0.data.args = {}
        action1.data.args = {}

        action0.data.user_id = posted_actions[0].data.user_id
        action1.data.user_id = posted_actions[1].data.user_id

        self.assertEqual(posted_actions[0].data.to_dict(), action0.data.to_dict())
        self.assertEqual(posted_actions[1].data.to_dict(), action1.data.to_dict())

        a0 = self.dart.get_action(posted_actions[0].id)
        a1 = self.dart.get_action(posted_actions[1].id)
        self.assertEqual(a0.data.to_dict(), action0.data.to_dict())
        self.assertEqual(a1.data.to_dict(), action1.data.to_dict())

        self.dart.delete_action(a0.id)
        self.dart.delete_action(a1.id)

        try:
            self.dart.get_action(a0.id)
        except DartRequestException as e0:
            self.assertEqual(e0.response.status_code, 404)
            try:
                self.dart.get_action(a1.id)
            except DartRequestException as e1:
                self.assertEqual(e1.response.status_code, 404)
                return

        self.fail('action should have been missing after delete!')

if __name__ == '__main__':
    unittest.main()
