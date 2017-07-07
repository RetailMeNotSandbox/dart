# must run pip install -e . in src/python folder before running this unit test
import unittest

from dart.model.action import Action
from dart.model.action import ActionData


class ActionModelTests(unittest.TestCase):

    def setUp(self):
        self.actionModel = Action()
        self.actionDataModel = ActionData(name="action data name", action_type_name="test")

    def test_empty_action_model(self):
        print self.actionModel
        self.assertEqual(str(self.actionModel), "updated='None', data='None', id='None', version_id='None', created='None'")


    def test_action_model_with_no_data(self):
        self.actionModel = Action(id="1", data={}, version_id=2)
        self.assertEqual(str(self.actionModel), "updated='None', data='{}', id='1', version_id='2', created='None'")

    def test_action_model_with_data(self):
        self.actionModel = Action(id="1", data=self.actionDataModel, version_id=2)
        self.assertEqual(self.actionModel.id, "1")
        self.assertEqual(self.actionModel.version_id, 2)
        self.assertEqual(self.actionModel.created, None)
        self.assertEqual(self.actionModel.updated, None)

        self.assertEqual(self.actionModel.data.first_in_workflow, False)
        self.assertEqual(self.actionModel.data.workflow_instance_id, None)
        self.assertEqual(self.actionModel.data.on_success_email, [])
        self.assertEqual(self.actionModel.data.workflow_id, None)
        self.assertEqual(self.actionModel.data.ecs_task_arn, None)
        self.assertEqual(self.actionModel.data.on_failure, 'DEACTIVATE')
        self.assertEqual(self.actionModel.data.user_id, 'anonymous')
        self.assertEqual(self.actionModel.data.order_idx, None)
        self.assertEqual(self.actionModel.data.state, 'HAS_NEVER_RUN')
        self.assertEqual(self.actionModel.data.workflow_action_id, None)
        self.assertEqual(self.actionModel.data.progress, None)
        self.assertEqual(self.actionModel.data.extra_data, None)
        self.assertEqual(self.actionModel.data.tags, [])
        self.assertEqual(self.actionModel.data.parallelization_idx, None)
        self.assertEqual(self.actionModel.data.batch_job_id, None)
        self.assertEqual(self.actionModel.data.start_time, None)
        self.assertEqual(self.actionModel.data.args, None)
        self.assertEqual(self.actionModel.data.last_in_workflow, False)
        self.assertEqual(self.actionModel.data.datastore_id, None)
        self.assertEqual(self.actionModel.data.on_failure_email, [])
        self.assertEqual(self.actionModel.data.avg_runtime, None)
        self.assertEqual(self.actionModel.data.name, 'action data name')
        self.assertEqual(self.actionModel.data.engine_name, None)
        self.assertEqual(self.actionModel.data.parallelization_parents, [])
        self.assertEqual(self.actionModel.data.error_message, None)
        self.assertEqual(self.actionModel.data.queued_time, None)
        self.assertEqual(self.actionModel.data.end_time, None)
        self.assertEqual(self.actionModel.data.action_type_name, 'test')
        self.assertEqual(self.actionModel.data.completed_runs, 0)
