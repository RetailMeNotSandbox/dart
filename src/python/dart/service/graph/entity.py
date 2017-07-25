# coding=utf-8
from collections import defaultdict
import json
import redis
import logging

from sqlalchemy import text

from dart.context.database import db_replica as db
from dart.context.locator import injectable
from dart.model.action import Action, ActionState
from dart.model.dataset import Dataset
from dart.model.datastore import Datastore
from dart.model.event import Event
from dart.model.graph import GraphEntity, Graph, Node, Edge, Relationship, GraphEntityIdentifier, SubGraph, EntityType, \
    SubGraphDefinition
from dart.model.orm import SubGraphDefinitionDao
from dart.model.subscription import Subscription
from dart.model.trigger import Trigger
from dart.model.workflow import Workflow
from dart.service.graph.sql_recursive import RECURSIVE_SQL
from dart.service.graph.sql_misc import ENTITY_IDENTIFIER_SQL, DATASTORE_ONE_OFFS_SQL, WORKFLOW_INSTANCE_SQL
from dart.service.graph.sub_graph import get_static_subgraphs_by_engine_name, \
    get_static_subgraphs_by_engine_name_all_engines_related_none
from dart.util.rand import random_id
from operator import is_not
from functools import partial
import ast

_logger = logging.getLogger(__name__)

@injectable
class GraphEntityService(object):
    def __init__(self, engine_service, datastore_service, action_service, dart_config):
        self._engine_service = engine_service
        self._datastore_service = datastore_service
        self._action_service = action_service

        self._dart_config = dart_config

        self.redis_expiration_ttl = 0
        self.redis_client = None
        if ('redis' in dart_config):
            redis_host = dart_config['redis']['host']
            redis_port = int(dart_config['redis']['port'])
            self.redis_expiration_ttl = int(dart_config['redis']['expire_seconds'])

            try:
                self.redis_client = None #redis.StrictRedis(host=redis_host, port=redis_port, db=0)
            except Exception as err:
                _logger.error("Redis: failed to create a redis client. err={0}".format(err))


    def get_sub_graphs(self, related_type, related_engine_name):
        engine = None
        if related_engine_name:
            engine = self._engine_service.get_engine_by_name(related_engine_name)

        # merging (dictionary of lists)'s is easier with defaultdict
        sub_graphs_by_engine_name = defaultdict(list)

        # static subgraphs for the specified engine (or no engine)
        static_sub_graphs_by_engine_name = get_static_subgraphs_by_engine_name(engine, related_type, self)
        sub_graphs_by_engine_name.update(static_sub_graphs_by_engine_name)

        # engine provided subgraphs from the database
        db_sub_graphs = self._get_db_subgraphs_by_engine_name(related_engine_name, related_type)
        for engine_name, sub_graphs in db_sub_graphs.iteritems():
            sub_graphs_by_engine_name[engine_name].extend(sub_graphs)

        # static sub_graphs that are related to None
        if related_type is None:
            engine_names = self._engine_service.all_engine_names()
            unrelated_sub_graphs = get_static_subgraphs_by_engine_name_all_engines_related_none(engine_names, self)
            for engine_name, sub_graphs in unrelated_sub_graphs.iteritems():
                sub_graphs_by_engine_name[engine_name].extend(sub_graphs)

        return sub_graphs_by_engine_name

    def _get_db_subgraphs_by_engine_name(self, related_engine_name, related_type):
        query = SubGraphDefinitionDao.query
        if related_engine_name:
            query = query.filter(SubGraphDefinitionDao.data['engine_name'].astext == related_engine_name)
        if related_type:
            query = query.filter(SubGraphDefinitionDao.data['related_type'].astext == related_type)
        else:
            query = query.filter(SubGraphDefinitionDao.data['related_type'] == 'null')

        sub_graph_map = {}
        for e in query.all():
            sg_def = e.to_model()
            assert isinstance(sg_def, SubGraphDefinition)
            entity_models = self.to_entity_models_with_randomized_ids(
                sg_def.data.actions +
                sg_def.data.datasets +
                sg_def.data.datastores +
                sg_def.data.events +
                sg_def.data.subscriptions +
                sg_def.data.triggers +
                sg_def.data.workflows
            )
            engine_name = sg_def.data.engine_name
            entity_type = sg_def.data.related_type
            sub_graph = SubGraph(
                name=sg_def.data.name,
                description=sg_def.data.description,
                related_type=entity_type,
                related_is_a=sg_def.data.related_is_a,
                graph=self.to_graph(engine_name, entity_models),
                entity_map=self.to_entity_map(entity_models),
                icon=sg_def.data.icon,
                md_icon=sg_def.data.md_icon,
            )
            if engine_name not in sub_graph_map:
                sub_graph_map[engine_name] = []
            sub_graph_map[engine_name].append(sub_graph)

        return sub_graph_map

    def to_graph(self, engine_name, entity_models):
        visited_nodes = set()
        visited_edges = set()
        nodes = []
        edges = []

        for entity in entity_models:
            if isinstance(entity, Dataset):
                self._add_node(nodes, visited_nodes, 'dataset', entity.id, entity.data.name, None, None)

            if isinstance(entity, Action):
                self._add_node(nodes, visited_nodes, 'action', entity.id, entity.data.name, entity.data.state, entity.data.action_type_name)
                if entity.data.args and 'dataset_id' in entity.data.args:
                    self._add_edge(edges, visited_edges, 'dataset', entity.data.args['dataset_id'], 'action', entity.id)
                if entity.data.args and 'subscription_id' in entity.data.args:
                    self._add_edge(edges, visited_edges, 'subscription', entity.data.args['subscription_id'], 'action', entity.id)
                if entity.data.workflow_id:
                    self._add_edge(edges, visited_edges, 'workflow', entity.data.workflow_id, 'action', entity.id)
                if entity.data.datastore_id:
                    self._add_edge(edges, visited_edges, 'datastore', entity.data.datastore_id, 'action', entity.id)

            if isinstance(entity, Workflow):
                self._add_node(nodes, visited_nodes, 'workflow', entity.id, entity.data.name, entity.data.state, None)
                if entity.data.datastore_id:
                    self._add_edge(edges, visited_edges, 'datastore', entity.data.datastore_id, 'workflow', entity.id)

            if isinstance(entity, Trigger):
                self._add_node(nodes, visited_nodes, 'trigger', entity.id, entity.data.name, entity.data.state, entity.data.trigger_type_name)
                if entity.data.workflow_ids:
                    for wf_id in entity.data.workflow_ids:
                        self._add_edge(edges, visited_edges, 'trigger', entity.id, 'workflow', wf_id)
                if entity.data.args and 'completed_trigger_ids' in entity.data.args:
                    for t_id in entity.data.args['completed_trigger_ids']:
                        self._add_edge(edges, visited_edges, 'trigger', t_id, 'trigger', entity.id)
                if entity.data.args and 'event_id' in entity.data.args:
                    self._add_edge(edges, visited_edges, 'event', entity.data.args['event_id'], 'trigger', entity.id)
                if entity.data.args and 'completed_workflow_id' in entity.data.args:
                    self._add_edge(edges, visited_edges, 'workflow', entity.data.args['completed_workflow_id'], 'trigger', entity.id)
                if entity.data.args and 'subscription_id' in entity.data.args:
                    self._add_edge(edges, visited_edges, 'subscription', entity.data.args['subscription_id'], 'trigger', entity.id)

            if isinstance(entity, Subscription):
                self._add_node(nodes, visited_nodes, 'subscription', entity.id, entity.data.name, entity.data.state, None)
                if entity.data.dataset_id:
                    self._add_edge(edges, visited_edges, 'dataset', entity.data.dataset_id, 'subscription', entity.id)

            if isinstance(entity, Event):
                self._add_node(nodes, visited_nodes, 'event', entity.id, entity.data.name, entity.data.state, None)

            if isinstance(entity, Datastore):
                self._add_node(nodes, visited_nodes, 'datastore', entity.id, entity.data.name, entity.data.state, engine_name)

        return Graph(nodes, edges)

    @staticmethod
    def get_entity_identifiers(search):
        statement = text(ENTITY_IDENTIFIER_SQL).bindparams(search=search)
        return [GraphEntityIdentifier(*r) for r in db.session.execute(statement)]

    def get_entity_graph(self, entity):
        """ :type entity: dart.model.graph.GraphEntity
            :rtype: dart.model.graph.Graph """

        key = "graph:{0}".format(entity.entity_id)
        cached_graph = self.redis_client.get(key) if self.redis_client else None  # String representation of each Graph record

        if cached_graph:
            json_records = json.loads(cached_graph)
            ### read state from database:
            # we need to update the current state of object in the graph
            get_state_sql = ["select '{0}' as type, '{1}' as id,'{2}' as name, data->>'state' as state, '{4}' as sub_type, '{5}' as related_type, '{6}' as related_id, '{7}' as related_is_a FROM {0} where id = '{1}'".format(*rec) for rec in json_records]

            # add union all between sql statements
            state_sql = " union all ".join(get_state_sql)

            # execute sql: (dart_depth was already removed, so we use r instead of r[0:-1])
            records = [(r) for r in db.session.execute(text(state_sql))]
        else:
            records = [
                (r[:-1])  # remove depth parameter
                for r in db.session.execute(text(RECURSIVE_SQL).bindparams(
                    entity_type=entity.entity_type,
                    entity_id=entity.entity_id,
                    name=entity.name,
                    state=entity.state,
                    sub_type=entity.sub_type
                ))
            ]
            string_records = json.dumps(records)
            if self.redis_client:
                self.redis_client.setex(key, self.redis_expiration_ttl, string_records)  # Keep this graph cached for 10 minutes


        # rebuilding graph from string
        entities = [GraphEntity(*r) for r in records]

        nodes, visited_nodes = [], set()
        edges, visited_edges = [], set()

        for e in entities:
            self._add_node(nodes, visited_nodes, e.entity_type, e.entity_id, e.name, e.state, e.sub_type)

            if e.related_id:
                if e.related_is_a == Relationship.CHILD:
                    src_type = e.entity_type
                    src_id = e.entity_id
                    dst_type = e.related_type
                    dst_id = e.related_id
                else:
                    src_type = e.related_type
                    src_id = e.related_id
                    dst_type = e.entity_type
                    dst_id = e.entity_id

                self._add_edge(edges, visited_edges, src_type, src_id, dst_type, dst_id)

        # now that we have the base graph, add in the most recent workflow_instances and their actions,
        # as well as recent datastore actions that are not associated with any workflows (if any)
        wf_ids, wf_sql = self._get_workflow_instance_sql(nodes)
        d_ids, d_sql = self._get_datastore_one_offs(nodes)

        sql_parts = []
        if wf_sql:
            sql_parts.append('(' + wf_sql + ')')
        if d_sql:
            sql_parts.append('(' + d_sql + ')')

        if len(sql_parts) == 0:
            return Graph(nodes, edges)

        sql = '\nUNION ALL\n'.join(sql_parts)
        statement = text(sql.format(
            wf_ids=', '.join(["'" + wf_id + "'" for wf_id in wf_ids]),
            d_ids=', '.join(["'" + d_id + "'" for d_id in d_ids])
        ))

        for r in db.session.execute(statement):
            if r[0] == 'workflow':
                entity_type, wf_id, wfi_id, wfi_state, a_id, a_name, a_state, a_sub_type = r

                name = 'workflow_instance'
                if wfi_state == 'RUNNING' and ('workflow_instance' + wfi_id) not in visited_nodes:
                    actions = self._action_service.find_actions(workflow_instance_id=wfi_id)
                    if None not in [a.data.avg_runtime for a in actions]:
                        wfi_progress = 0
                        wf_runtime = 0
                        for a in actions:
                            a_runtime = a.data.avg_runtime.total_seconds()
                            wf_runtime += a_runtime
                            if a.data.state == ActionState.COMPLETED or a.data.state == ActionState.FAILED:
                                wfi_progress += a_runtime
                            elif (a.data.state == ActionState.RUNNING or a.data.state == ActionState.FINISHING) and a.data.progress:
                                wfi_progress += a_runtime * a.data.progress
                        if wf_runtime:
                            wfi_progress /= wf_runtime
                            name += ' - {:.0%}'.format(wfi_progress)

                self._add_node(nodes, visited_nodes, 'workflow_instance', wfi_id, name, wfi_state, None)
                self._add_edge(edges, visited_edges, 'workflow', wf_id, 'workflow_instance', wfi_id)
                if a_id:
                    self._add_node(nodes, visited_nodes, 'action', a_id, a_name, a_state, a_sub_type)
                    self._add_edge(edges, visited_edges, 'workflow_instance', wfi_id, 'action', a_id)
            else:
                entity_type, d_id, skip1, skip2, a_id, a_name, a_state, a_sub_type = r
                self._add_node(nodes, visited_nodes, 'action', a_id, a_name, a_state, a_sub_type)
                self._add_edge(edges, visited_edges, 'datastore', d_id, 'action', a_id)

        self.add_MM_nodes(nodes=nodes, edges=edges, visited_edges=visited_edges)
        return Graph(nodes, edges)

    def add_MM_nodes(self, nodes, edges, visited_edges):
        ''' MasterMind migrated workflows will want to show parent-child relationships between action nodes.
            We will show parent-child relationships only if the parallization parents exist (new workflows).
        '''
        def str_2_list(list_str):
            ''' '[1,2,3]' => [1,2,3] '''
            try:
                x = ast.literal_eval(list_str)
                return x
            except Exception as err:
                _logger.warning(err)
                return []

        def to_int(str):
            ''' "2.0" => 2 '''
            return int(float(str))

        # The template actions have the original order_idx (the instance action increment them constantly).
        # Instance action have mappings to their template actions via data->>'workflow_action_id'.
        # We match each template action with its instance action, and each parent template action with its matching
        # parent instance action.  For each such opair we add an edge.
        # In order de-clutter the graph we also remove edges from workflow and workflow-action to nodes
        # (except the first ones)

        # create template_action_id_2_instance_action which helps get an instance action by its template action id.
        WFI_IDS_SQL = "select  data->>'workflow_action_id', id, data->>'workflow_instance_id', data->>'workflow_id' from action where data->>'state'::TEXT != 'TEMPLATE' and data->>'workflow_instance_id' in ({0})"
        workflow_instance_ids = list(filter(partial(is_not, None),[n.entity_id if n.entity_type=='workflow_instance' else None for n in nodes]))
        wfi_ids = ','.join("'{0}'".format(w) for w in workflow_instance_ids)
        template_action_id_2_instance_action = {}
        if wfi_ids:
            for instance_action in db.session.execute(WFI_IDS_SQL.format(wfi_ids)):
                template_action_id_2_instance_action[instance_action[0]] = instance_action

        # For each workflow, find its actions and if action has parents than add edges from parent to child.
        WF_IDS_SQL = "SELECT id, data->>'order_idx' as idx, data->>'parallelization_parents' AS parents FROM action WHERE data->>'workflow_id'='{0}' and data->>'state'::TEXT = 'TEMPLATE'"
        workflow_ids = list(filter(partial(is_not, None),[n.entity_id if n.entity_type=='workflow' else None for n in nodes]))
        order_idx_2_template_action = {}
        template_action_id_2_order_idx = {}
        for wf_id in workflow_ids:
            # populate the two dictionaries above for the template actions only
            for action_record in db.session.execute(WF_IDS_SQL.format(wf_id)):
                order_idx_2_template_action[to_int(action_record[1])] = action_record
                template_action_id_2_order_idx[action_record[0]] = to_int(action_record[1])

            # For every template action (which may have an associated instance action) add an edge to parent (if exists)
            for act in order_idx_2_template_action.values():
                action_parents_str = act[2]
                if action_parents_str:  # if has parents (as order_idx values
                    template_action_id = act[0]

                    matching_instance_workflow_id = None
                    matching_instance_workflow_id = None
                    if template_action_id_2_instance_action.get(template_action_id):
                        matching_instance_action_id = template_action_id_2_instance_action.get(template_action_id)[1]
                        matching_instance_workflow_id = template_action_id_2_instance_action.get(template_action_id)[2]

                    # At this point we know we have parents for the template actions. We will add edges for the template
                    # actions and their matching instance actions (and parents) in tandem using mappings above.
                    for parents_idx in str_2_list(action_parents_str):
                        parent = order_idx_2_template_action.get(to_int(parents_idx))
                        if parent:
                            # In order to make the graph less cluttered we keep the workflow node pointing to
                            # the first template action only.
                            self._remove_edge(edges, visited_edges, "workflow", wf_id, "action", template_action_id)
                            if matching_instance_workflow_id:
                                self._remove_edge(edges, visited_edges, "workflow_instance", matching_instance_workflow_id, "action", matching_instance_action_id)

                            parent_template_action_id = parent[0]
                            self._add_edge(edges, visited_edges, 'action', parent_template_action_id, 'action', template_action_id)
                            if template_action_id_2_instance_action.get(parent_template_action_id):
                                parent_instance_action_id = template_action_id_2_instance_action.get(parent_template_action_id)[1]
                                if matching_instance_action_id:
                                    self._add_edge(edges, visited_edges, 'action', parent_instance_action_id, 'action', matching_instance_action_id)

    @staticmethod
    def _get_datastore_one_offs(nodes):
        d_sql = ''
        d_ids = [n.entity_id for n in nodes if n.entity_type == 'datastore']
        if len(d_ids) > 0:
            d_sql = DATASTORE_ONE_OFFS_SQL
        return d_ids, d_sql

    @staticmethod
    def _get_workflow_instance_sql(nodes):
        wf_sql = ''
        wf_ids = [n.entity_id for n in nodes if n.entity_type == 'workflow']
        if len(wf_ids) > 0:
            wf_sql = WORKFLOW_INSTANCE_SQL
        return wf_ids, wf_sql

    @staticmethod
    def _add_node(nodes, visited_nodes, e_type, e_id, name, state, sub_type):
        node_id = e_type + '-' + e_id
        if node_id not in visited_nodes:
            visited_nodes.add(node_id)
            nodes.append(Node(e_type, e_id, name, state, sub_type))

    @staticmethod
    def _add_edge(edges, visited_edges, s_type, s_id, d_type, d_id):
        edge_id = '%s-%s %s-%s' % (s_type, s_id, d_type, d_id)
        if edge_id not in visited_edges:
            visited_edges.add(edge_id)
            edges.append(Edge(s_type, s_id, d_type, d_id))

    @staticmethod
    def _remove_edge(edges, visited_edges, s_type, s_id, d_type, d_id):
        edge_id = '%s-%s %s-%s' % (s_type, s_id, d_type, d_id)
        found_item = False
        if edge_id in visited_edges:
            for idx, e in enumerate(edges):
                if (e.source_type == s_type) and (e.source_id == s_id) and (e.destination_type == d_type) and (e.destination_id == d_id):
                    found_item = True
                    break

        if found_item:
            del edges[idx]

    @staticmethod
    def _get_entity_type(entity):
        if isinstance(entity, Dataset):
            return EntityType.dataset
        if isinstance(entity, Action):
            return EntityType.action
        if isinstance(entity, Workflow):
            return EntityType.workflow
        if isinstance(entity, Trigger):
            return EntityType.trigger
        if isinstance(entity, Subscription):
            return EntityType.subscription
        if isinstance(entity, Event):
            return EntityType.event
        if isinstance(entity, Datastore):
            return EntityType.datastore

    def to_entity_map(self, entity_models):
        return {self._get_entity_type(em) + '-' + em.id: em for em in entity_models}

    @staticmethod
    def to_entity_models_with_randomized_ids(entity_models):
        # To support editing multiple subgraphs concurrently, we need to randomize the ids.
        # This method takes advantage of JSON formatting (a bit hacky, but simple and fast).
        id_map = {}
        for e in entity_models:
            prefix = 'UNSAVED'
            if e.id.startswith('PARENT'):
                prefix = 'PARENT'
            if e.id.startswith('CHILD'):
                prefix = 'CHILD'
            id_map[e.id] = '%s-%s' % (prefix, random_id())

        results = []
        for em in entity_models:
            stringified_model = json.dumps(em.to_dict())
            for original_id, randomized_id in id_map.iteritems():
                stringified_model = stringified_model.replace('"%s"' % original_id, '"%s"' % randomized_id)
            cls = type(em)
            results.append(cls.from_dict(json.loads(stringified_model)))
        return results
