import copy
import json
import logging
import traceback
from dart.context.database import db
from dart.context.locator import injectable
from dart.model.action import Action
from dart.model.dataset import Dataset
from dart.model.datastore import Datastore
from dart.model.event import Event
from dart.model.graph import EntityType, Relationship, Edge
from dart.model.subscription import Subscription
from dart.model.trigger import Trigger
from dart.model.workflow import Workflow
from dart.trigger.super import super_trigger


_logger = logging.getLogger(__name__)


@injectable
class GraphEntityResolverService(object):
    def __init__(self, dataset_service, datastore_service, event_service, subscription_service, workflow_service,
                 action_service, trigger_service, trigger_proxy):
        self._dataset_service = dataset_service
        self._datastore_service = datastore_service
        self._event_service = event_service
        self._subscription_service = subscription_service
        self._workflow_service = workflow_service
        self._action_service = action_service
        self._trigger_service = trigger_service
        self._trigger_proxy = trigger_proxy
        self._resolvers = {
            EntityType.dataset: self._resolve_and_save_dataset,
            EntityType.datastore: self._resolve_and_save_datastore,
            EntityType.event: self._resolve_and_save_event,
            EntityType.subscription: self._resolve_and_save_subscription,
            EntityType.workflow: self._resolve_and_save_workflow,
            EntityType.action: self._resolve_and_save_action,
            EntityType.trigger: self._resolve_and_save_trigger,
        }

    def save_entities(self, entity_map, debug=False):
        """ :type entity_map: dict """

        actual_entities_by_node_id = {}
        actual_entities_by_unsaved_id = {}

        # =========================================================================================================
        # todo: do basic validation and bail early if there are issues
        # =========================================================================================================
        pass

        try:
            for node_id in entity_map['unsaved_entities'].keys():
                entity_type = self._entity_type(node_id)
                entity_id = self._entity_id(node_id)
                resolve_and_save_func = self._resolvers[entity_type]
                resolve_and_save_func(entity_id, entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id)

            self.update_related_triggers(entity_map)

            db.session.commit()

            affected_datastore_ids = set()
            for node_id, entity in actual_entities_by_node_id.iteritems():
                try:
                    entity_type = self._entity_type(node_id)
                    if entity_type == EntityType.datastore:
                        self._datastore_service.handle_datastore_state_change(entity, None, entity.data.state)
                    if entity_type == EntityType.subscription:
                        self._subscription_service.generate_subscription_elements(entity)
                    if entity_type == EntityType.trigger:
                        self._trigger_service.initialize_trigger(entity)
                    if entity_type == EntityType.action:
                        assert isinstance(entity, Action)
                        if entity.data.datastore_id:
                            affected_datastore_ids.add(entity.data.datastore_id)
                except Exception:
                    _logger.error(json.dumps(traceback.format_exc()))

            for datastore_id in affected_datastore_ids:
                try:
                    self._trigger_proxy.try_next_action({'datastore_id':datastore_id})
                except Exception:
                    _logger.error(json.dumps(traceback.format_exc()))

            return actual_entities_by_node_id, None

        except Exception as e:
            db.session.rollback()
            if debug:
                return None, json.dumps(traceback.format_exc())
            return None, e.message

    def _resolve_and_save_dataset(self, entity_id, entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id):
        actual_id, unsaved_id = self._resolve(EntityType.dataset, entity_id, entity_map, actual_entities_by_unsaved_id)
        if actual_id:
            return actual_id
        node_id = self._node_id(EntityType.dataset, unsaved_id)
        dataset = Dataset.from_dict(entity_map['unsaved_entities'][node_id])
        dataset = self._dataset_service.save_dataset(dataset, commit=False, flush=True)
        actual_entities_by_node_id[node_id] = dataset
        actual_entities_by_unsaved_id[unsaved_id] = dataset
        return dataset.id

    def _resolve_and_save_datastore(self, entity_id, entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id):
        actual_id, unsaved_id = self._resolve(EntityType.datastore, entity_id, entity_map, actual_entities_by_unsaved_id)
        if actual_id:
            return actual_id
        node_id = self._node_id(EntityType.datastore, unsaved_id)
        datastore = Datastore.from_dict(entity_map['unsaved_entities'][node_id])
        datastore = self._datastore_service.save_datastore(datastore, commit_and_handle_state_change=False, flush=True)
        actual_entities_by_node_id[node_id] = datastore
        actual_entities_by_unsaved_id[unsaved_id] = datastore
        return datastore.id

    def _resolve_and_save_event(self, entity_id, entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id):
        actual_id, unsaved_id = self._resolve(EntityType.event, entity_id, entity_map, actual_entities_by_unsaved_id)
        if actual_id:
            return actual_id
        node_id = self._node_id(EntityType.event, unsaved_id)
        event = Event.from_dict(entity_map['unsaved_entities'][node_id])
        event = self._event_service.save_event(event, commit=False, flush=True)
        actual_entities_by_node_id[node_id] = event
        actual_entities_by_unsaved_id[unsaved_id] = event
        return event.id

    def _resolve_and_save_subscription(self, entity_id, entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id):
        actual_id, unsaved_id = self._resolve(EntityType.subscription, entity_id, entity_map, actual_entities_by_unsaved_id)
        if actual_id:
            return actual_id
        node_id = self._node_id(EntityType.subscription, unsaved_id)
        subscription = Subscription.from_dict(entity_map['unsaved_entities'][node_id])
        assert isinstance(subscription, Subscription)
        subscription.data.dataset_id = self._resolve_and_save_dataset(subscription.data.dataset_id, entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id)
        subscription = self._subscription_service.save_subscription(subscription, commit_and_generate=False, flush=True)
        actual_entities_by_node_id[node_id] = subscription
        actual_entities_by_unsaved_id[unsaved_id] = subscription
        return subscription.id

    def _resolve_and_save_workflow(self, entity_id, entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id):
        actual_id, unsaved_id = self._resolve(EntityType.workflow, entity_id, entity_map, actual_entities_by_unsaved_id)
        if actual_id:
            return actual_id
        node_id = self._node_id(EntityType.workflow, unsaved_id)
        workflow = Workflow.from_dict(entity_map['unsaved_entities'][node_id])
        assert isinstance(workflow, Workflow)
        workflow.data.datastore_id = self._resolve_and_save_datastore(workflow.data.datastore_id, entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id)
        workflow = self._workflow_service.save_workflow(workflow, commit=False, flush=True)
        actual_entities_by_node_id[node_id] = workflow
        actual_entities_by_unsaved_id[unsaved_id] = workflow
        return workflow.id

    def _resolve_and_save_action(self, entity_id, entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id):
        actual_id, unsaved_id = self._resolve(EntityType.action, entity_id, entity_map, actual_entities_by_unsaved_id)
        if actual_id:
            return actual_id
        node_id = self._node_id(EntityType.action, unsaved_id)
        action = Action.from_dict(entity_map['unsaved_entities'][node_id])
        assert isinstance(action, Action)
        if action.data.datastore_id:
            action.data.datastore_id = self._resolve_and_save_datastore(action.data.datastore_id, entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id)
        if action.data.workflow_id:
            action.data.workflow_id = self._resolve_and_save_workflow(action.data.workflow_id, entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id)
        if action.data.args and action.data.args.get('subscription_id'):
            action.data.args['subscription_id'] = self._resolve_and_save_subscription(action.data.args['subscription_id'], entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id)
        if action.data.args and action.data.args.get('dataset_id'):
            action.data.args['dataset_id'] = self._resolve_and_save_dataset(action.data.args['dataset_id'], entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id)
        engine_name, datastore = self._find_engine_name_and_datastore(action)
        action = self._action_service.save_actions([action], engine_name, datastore, commit=False, flush=True)[0]
        actual_entities_by_node_id[node_id] = action
        actual_entities_by_unsaved_id[unsaved_id] = action
        return action.id

    def _resolve_and_save_trigger(self, entity_id, entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id):
        actual_id, unsaved_id = self._resolve(EntityType.trigger, entity_id, entity_map, actual_entities_by_unsaved_id)
        if actual_id:
            return actual_id
        node_id = self._node_id(EntityType.trigger, unsaved_id)
        trigger = Trigger.from_dict(entity_map['unsaved_entities'][node_id])
        assert isinstance(trigger, Trigger)
        if trigger.data.args and trigger.data.args.get('completed_workflow_id'):
            trigger.data.args['completed_workflow_id'] = self._resolve_and_save_workflow(trigger.data.args['completed_workflow_id'], entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id)
        if trigger.data.args and trigger.data.args.get('event_id'):
            trigger.data.args['event_id'] = self._resolve_and_save_event(trigger.data.args['event_id'], entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id)
        if trigger.data.args and trigger.data.args.get('subscription_id'):
            trigger.data.args['subscription_id'] = self._resolve_and_save_subscription(trigger.data.args['subscription_id'], entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id)
        if trigger.data.workflow_ids:
            wf_ids = set()
            for wf_id in trigger.data.workflow_ids:
                wf_ids.add(self._resolve_and_save_workflow(wf_id, entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id))
            trigger.data.workflow_ids = list(wf_ids)
        if trigger.data.args.get('completed_trigger_ids'):
            t_ids = set()
            for t_id in trigger.data.args['completed_trigger_ids']:
                t_ids.add(self._resolve_and_save_trigger(t_id, entity_map, actual_entities_by_node_id, actual_entities_by_unsaved_id))
            trigger.data.args['completed_trigger_ids'] = list(t_ids)
        trigger = self._trigger_service.save_trigger(trigger, commit_and_initialize=False, flush=True)
        actual_entities_by_node_id[node_id] = trigger
        actual_entities_by_unsaved_id[unsaved_id] = trigger
        return trigger.id

    def update_related_triggers(self, entity_map):
        for entity_data in entity_map.get('related_entity_data', {}).values():
            if entity_data['entity_type'] != EntityType.trigger:
                continue
            if self._is_a_reference(entity_data['entity_id']):
                continue
            edge = Edge.from_dict(entity_data['edge'])
            assert isinstance(edge, Edge)

            if entity_data['relationship'] == Relationship.PARENT:
                assert edge.destination_type == EntityType.workflow
                trigger = self._trigger_service.get_trigger(edge.source_id)
                updated_workflow_ids = list(set((trigger.data.workflow_ids or []) + [edge.destination_id]))
                self._trigger_service.update_trigger_workflow_ids(trigger, updated_workflow_ids)

            if entity_data['relationship'] == Relationship.CHILD:
                assert edge.source_type == EntityType.trigger
                s_trigger = self._trigger_service.get_trigger(edge.destination_id)
                assert s_trigger.data.trigger_type_name == super_trigger.name
                updated_args = copy.deepcopy(s_trigger.data.args)
                updated_args['completed_trigger_ids'] = list(set(
                    updated_args['completed_trigger_ids'] + [edge.source_id]
                ))
                self._trigger_service.update_trigger_args(s_trigger, updated_args)

    @staticmethod
    def _entity_type(node_id):
        return node_id.split('-', 1)[0]

    @staticmethod
    def _entity_id(node_id):
        return node_id.split('-', 1)[1]

    @staticmethod
    def _node_id(entity_type, entity_id):
        return entity_type + '-' + entity_id

    @staticmethod
    def _is_a_reference(entity_id):
        return 'UNSAVED-' in entity_id or 'PARENT-' in entity_id or 'CHILD-' in entity_id

    def _resolve(self, entity_type, entity_id, entity_map, actual_entities_by_unsaved_id):
        if not self._is_a_reference(entity_id):
            return entity_id, None
        if entity_id in actual_entities_by_unsaved_id:
            return actual_entities_by_unsaved_id[entity_id].id, None
        if entity_id.startswith('UNSAVED-'):
            return None, entity_id
        if entity_id.startswith('PARENT-') or entity_id.startswith('CHILD-'):
            related = entity_map['related_entity_data'][self._node_id(entity_type, entity_id)]
            return self._resolve(entity_type, related['entity_id'], entity_map, actual_entities_by_unsaved_id)
        raise Exception('could not resolve entity: %s-%s' % (entity_type, entity_id))

    def _find_engine_name_and_datastore(self, action):
        """ :type action: dart.model.action.Action """
        datastore_id = action.data.datastore_id
        if datastore_id:
            datastore = self._datastore_service.get_datastore(datastore_id)
            return datastore.data.engine_name, datastore

        workflow_id = action.data.workflow_id
        if workflow_id:
            workflow = self._workflow_service.get_workflow(workflow_id)
            datastore = self._datastore_service.get_datastore(workflow.data.datastore_id)
            return datastore.data.engine_name, datastore

        raise Exception('could not find datastore from action :%s' % action.id)
