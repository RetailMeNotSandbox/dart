from dart.util.logging_utils import DartLogger
import os
from dart.client.python.dart_client import Dart
from dart.config.config import configuration
from dart.engine.emr.metadata import EmrActionTypes
from dart.model.action import Action, ActionData, ActionState
from dart.model.graph import SubGraphDefinition, EntityType, Relationship, Ref, SubGraphDefinitionData
from dart.model.subscription import Subscription, SubscriptionData
from dart.model.trigger import Trigger, TriggerData
from dart.model.workflow import Workflow, WorkflowData
from dart.trigger.subscription import subscription_batch_trigger

_logger = DartLogger(__name__)


def add_emr_engine_sub_graphs(config):
    engine_config = config['engines']['emr_engine']
    opts = engine_config['options']
    dart = Dart(opts['dart_host'], opts['dart_port'], opts['dart_api_version'])
    assert isinstance(dart, Dart)

    _logger.info('saving emr_engine sub_graphs')

    engine_id = None
    for e in dart.get_engines():
        if e.data.name == 'emr_engine':
            engine_id = e.id
    if not engine_id:
        raise

    subgraph_definitions = [
        SubGraphDefinition(data=SubGraphDefinitionData(
            name='consume_subscription_workflow',
            description='Add to a datastore to create entities for loading a dataset on an ongoing basis',
            engine_name='emr_engine',
            related_type=EntityType.datastore,
            related_is_a=Relationship.PARENT,
            workflows=[
                Workflow(id=Ref.workflow(1), data=WorkflowData(
                    name='emr-workflow-consume_subscription',
                    datastore_id=Ref.parent(),
                    engine_name='emr_engine',
                )),
            ],
            subscriptions=[
                Subscription(id=Ref.subscription(1), data=SubscriptionData(
                    name='emr-subscription',
                    dataset_id=''
                )),
            ],
            triggers=[
                Trigger(id=Ref.trigger(1), data=TriggerData(
                    name='emr-trigger-subscription-1G-batch',
                    trigger_type_name=subscription_batch_trigger.name,
                    workflow_ids=[Ref.workflow(1)],
                    args={
                        'subscription_id': Ref.subscription(1),
                        'unconsumed_data_size_in_bytes': 1000*1000*1000
                    }
                )),
            ],
            actions=[
                Action(id=Ref.action(1), data=ActionData(
                    name='emr-action-consume_subscription',
                    action_type_name=EmrActionTypes.consume_subscription.name,
                    engine_name='emr_engine',
                    workflow_id=Ref.workflow(1),
                    state=ActionState.TEMPLATE,
                    args={'subscription_id': Ref.subscription(1)}
                )),
            ]
        ))
    ]

    for e in subgraph_definitions:
        s = dart.save_subgraph_definition(e, engine_id)
        _logger.info('created subgraph_definition: %s' % s.id)


if __name__ == '__main__':
    add_emr_engine_sub_graphs(configuration(os.environ['DART_CONFIG']))
