from dart.util.logging_utils import DartLogger
import os
from dart.client.python.dart_client import Dart
from dart.config.config import configuration
from dart.engine.no_op.metadata import NoOpActionTypes
from dart.model.action import Action, ActionData, ActionState
from dart.model.graph import SubGraphDefinition, EntityType, Relationship, Ref, SubGraphDefinitionData
from dart.model.trigger import Trigger, TriggerData, TriggerState
from dart.model.workflow import Workflow, WorkflowData, WorkflowState
from dart.trigger.workflow import workflow_completion_trigger

_logger = DartLogger(__name__)


def add_no_op_engine_sub_graphs(config):
    engine_config = config['engines']['no_op_engine']
    opts = engine_config['options']
    dart = Dart(opts['dart_host'], opts['dart_port'], opts['dart_api_version'])
    assert isinstance(dart, Dart)

    _logger.info('saving no_op_engine sub_graphs')

    engine_id = None
    for e in dart.get_engines():
        if e.data.name == 'no_op_engine':
            engine_id = e.id
    if not engine_id:
        raise

    subgraph_definitions = [
        SubGraphDefinition(data=SubGraphDefinitionData(
            name='workflow chaining demo',
            description='demonstrate workflow chaining',
            engine_name='no_op_engine',
            related_type=EntityType.datastore,
            related_is_a=Relationship.PARENT,
            workflows=[
                Workflow(id=Ref.workflow(1), data=WorkflowData(
                    name='no-op-workflow-chaining-wf1',
                    datastore_id=Ref.parent(),
                    engine_name='no_op_engine',
                    state=WorkflowState.ACTIVE,
                )),
                Workflow(id=Ref.workflow(2), data=WorkflowData(
                    name='no-op-workflow-chaining-wf2',
                    datastore_id=Ref.parent(),
                    engine_name='no_op_engine',
                    state=WorkflowState.ACTIVE,
                )),
            ],
            actions=[
                Action(id=Ref.action(1), data=ActionData(
                    name=NoOpActionTypes.action_that_succeeds.name,
                    engine_name='no_op_engine',
                    action_type_name=NoOpActionTypes.action_that_succeeds.name,
                    workflow_id=Ref.workflow(1),
                    order_idx=1,
                    state=ActionState.TEMPLATE,
                )),
                Action(id=Ref.action(2), data=ActionData(
                    name=NoOpActionTypes.action_that_succeeds.name,
                    action_type_name=NoOpActionTypes.action_that_succeeds.name,
                    engine_name='no_op_engine',
                    workflow_id=Ref.workflow(1),
                    order_idx=2,
                    state=ActionState.TEMPLATE,
                )),
                Action(id=Ref.action(3), data=ActionData(
                    name=NoOpActionTypes.action_that_succeeds.name,
                    action_type_name=NoOpActionTypes.action_that_succeeds.name,
                    engine_name='no_op_engine',
                    workflow_id=Ref.workflow(1),
                    order_idx=3,
                    state=ActionState.TEMPLATE,
                )),
                Action(id=Ref.action(4), data=ActionData(
                    name=NoOpActionTypes.action_that_succeeds.name,
                    action_type_name=NoOpActionTypes.action_that_succeeds.name,
                    engine_name='no_op_engine',
                    workflow_id=Ref.workflow(1),
                    order_idx=4,
                    state=ActionState.TEMPLATE,
                )),
                Action(id=Ref.action(5), data=ActionData(
                    name=NoOpActionTypes.action_that_succeeds.name,
                    action_type_name=NoOpActionTypes.action_that_succeeds.name,
                    engine_name='no_op_engine',
                    workflow_id=Ref.workflow(2),
                    order_idx=1,
                    state=ActionState.TEMPLATE,
                )),
                Action(id=Ref.action(6), data=ActionData(
                    name=NoOpActionTypes.action_that_succeeds.name,
                    action_type_name=NoOpActionTypes.action_that_succeeds.name,
                    engine_name='no_op_engine',
                    workflow_id=Ref.workflow(2),
                    order_idx=2,
                    state=ActionState.TEMPLATE,
                )),
                Action(id=Ref.action(7), data=ActionData(
                    name=NoOpActionTypes.action_that_fails.name,
                    action_type_name=NoOpActionTypes.action_that_fails.name,
                    engine_name='no_op_engine',
                    workflow_id=Ref.workflow(2),
                    order_idx=3,
                    state=ActionState.TEMPLATE,
                )),
            ],
            triggers=[
                Trigger(id=Ref.trigger(1), data=TriggerData(
                    name='no-op-trigger-workflow-completion',
                    trigger_type_name=workflow_completion_trigger.name,
                    workflow_ids=[Ref.workflow(2)],
                    state=TriggerState.ACTIVE,
                    args={'completed_workflow_id': Ref.workflow(1)}
                )),
            ],
        ))
    ]

    for e in subgraph_definitions:
        s = dart.save_subgraph_definition(e, engine_id)
        _logger.info('created subgraph_definition: %s' % s.id)


if __name__ == '__main__':
    add_no_op_engine_sub_graphs(configuration(os.environ['DART_CONFIG']))
