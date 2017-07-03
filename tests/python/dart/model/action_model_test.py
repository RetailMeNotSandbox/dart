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
        self.assertEqual(str(self.actionModel), "updated='None', data='first_in_workflow='False', workflow_instance_id='None', on_success_email='[]', workflow_id='None', ecs_task_arn='None', on_failure='DEACTIVATE', user_id='anonymous', order_idx='None', parallelization_parents='[]', state='HAS_NEVER_RUN', workflow_action_id='None', progress='None', extra_data='None', tags='[]', batch_job_id='None', start_time='None', args='None', last_in_workflow='False', datastore_id='None', on_failure_email='[]', avg_runtime='None', name='action data name', engine_name='None', error_message='None', queued_time='None', end_time='None', action_type_name='test', completed_runs='0'', id='1', version_id='2', created='None'")
