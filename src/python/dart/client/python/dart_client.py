import os
import json
import time

import jsonpatch
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from basicauth import encode

from dart.model.action import Action, ActionState
from dart.model.dataset import Dataset
from dart.model.datastore import Datastore
from dart.model.engine import Engine, ActionContext
from dart.model.event import Event
from dart.model.exception import DartRequestException
from dart.model.graph import Graph, SubGraphDefinition
from dart.model.query import Filter
from dart.model.query import Operator
from dart.model.subscription import Subscription, SubscriptionElementStats, SubscriptionState, SubscriptionElement
from dart.model.trigger import Trigger, TriggerType
from dart.model.workflow import Workflow, WorkflowInstance, WorkflowInstanceState
from dart.config.config import configuration

config_path = os.environ['DART_CONFIG']
config = configuration(config_path)
auth_config = config['auth']

# Disable 'InsecureRequestWarning: Unverified HTTPS request is being made...' warnings in local dev mode.
if auth_config.get('use_auth') and (auth_config.get('dart_server') == 'https://localhost:5000'):
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class Dart(object):

    def __init__(self, host, port=80, api_version=1):
        self._host = host
        self._port = port
        self._api_version = api_version
        self._base_url = '://%s:%s/api/%s' % (self._host, self._port, self._api_version)

        # We cannot access the user-id from the session (since no session exists).
        # AS a result we cannot access apikey/secret for user in db.
        # This makes sense since the client should already retrieved his keys from the database.
        # We will expose the key/secret via config variables.
        # These dart_client_key/dart_client_secret should be used by the dart_client only.
        # These values will be set during web worker startup (call to server.py) in user/apikey tables.
        if auth_config.get('use_auth'):
            if auth_config.get('dart_client_key') and auth_config.get('dart_client_secret'):
                self._credential = auth_config.get('dart_client_key')
                self._secret = auth_config.get('dart_client_secret')
                self._base_url = 'https' +  self._base_url
            else:
                raise DartRequestException("dart_client_key and dart_client_secret must both exist.")
        else:
            # The credential/secret default values are set in order to prevent exception while calculating to hmac.
            # The base url is http since no https end point will exist (local dev only)
            self._credential = "cred"
            self._secret = "secret"
            self._base_url = 'http' + self._base_url


    def save_engine(self, engine):
        """ :type engine: dart.model.engine.Engine
            :rtype: dart.model.engine.Engine """
        if engine.id:
            return self._request('put', '/engine/%s' % engine.id, data=engine.to_dict(), model_class=Engine)
        return self._request('post', '/engine', data=engine.to_dict(), model_class=Engine)

    def get_engine(self, engine_id):
        """ :type engine_id: str
            :rtype: dart.model.engine.Engine """
        return self._request('get', '/engine/%s' % engine_id, model_class=Engine)

    def get_engines(self):
        """ :rtype: list[dart.model.engine.Engine] """
        return self._request_list('get', '/engine', model_class=Engine)

    def save_subgraph_definition(self, subgraph_definition, engine_id):
        """ :type engine_id: str
            :type subgraph_definition: dart.model.graph.SubGraphDefinition
            :rtype: dart.model.graph.SubGraphDefinition """
        return self._request('post', '/engine/%s/subgraph_definition' % engine_id, data=subgraph_definition.to_dict(), model_class=SubGraphDefinition)

    def get_subgraph_definition(self, subgraph_definition_id):
        """ :type subgraph_definition_id: str
            :rtype: dart.model.subgraph_definition.Engine """
        return self._request('get', '/subgraph_definition/%s' % subgraph_definition_id, model_class=SubGraphDefinition)

    def get_subgraph_definitions(self, engine_id):
        """ :rtype: list[dart.model.graph.SubGraphDefinition] """
        return self._request_list('get', '/engine/%s/subgraph_definition' % engine_id, model_class=SubGraphDefinition)

    def engine_action_checkout(self, action_id):
        """ :type action_id: str
            :rtype: dart.model.engine.ActionContext """
        assert action_id is not None, 'action_id must be provided'
        return self._request('put', '/engine/action/%s/checkout' % action_id, None, model_class=ActionContext)

    def engine_action_checkin(self, action_id, action_result):
        """ :type action_id: str
            :type action_result: dart.model.engine.ActionResult
            :rtype: dict """
        return self._get_response_data('put', '/engine/action/%s/checkin' % action_id, data=action_result.to_dict())

    def delete_engine(self, engine_id):
        """ :type engine_id: str """
        self._get_response_data('delete', '/engine/%s' % engine_id)

    def save_dataset(self, dataset):
        """ :type dataset: dart.model.dataset.Dataset
            :rtype: dart.model.dataset.Dataset """
        if dataset.id:
            return self._request('put', '/dataset/%s' % dataset.id, data=dataset.to_dict(), model_class=Dataset)
        return self._request('post', '/dataset', data=dataset.to_dict(), model_class=Dataset)

    def get_dataset(self, dataset_id):
        """ :type dataset_id: str
            :rtype: dart.model.dataset.Dataset """
        return self._request('get', '/dataset/%s' % dataset_id, model_class=Dataset)

    def delete_dataset(self, dataset_id):
        """ :type dataset_id: str """
        self._get_response_data('delete', '/dataset/%s' % dataset_id)

    def save_datastore(self, datastore):
        """ :type datastore: dart.model.datastore.Datastore
            :rtype: dart.model.datastore.Datastore """
        if datastore.id:
            return self._request('put', '/datastore/%s' % datastore.id, data=datastore.to_dict(), model_class=Datastore)
        return self._request('post', '/datastore', data=datastore.to_dict(), model_class=Datastore)

    def get_datastore(self, datastore_id):
        """ :type datastore_id: str
            :rtype: dart.model.datastore.Datastore """
        return self._request('get', '/datastore/%s' % datastore_id, model_class=Datastore)

    def patch_datastore(self, datastore, **data_properties):
        """ :type action: dart.model.datastore.Datastore
            :rtype: dart.model.datastore.Datastore """
        p = self._get_patch(datastore, data_properties)
        return self._request('patch', '/datastore/%s' % datastore.id, data=p.patch, model_class=Datastore)

    def delete_datastore(self, datastore_id):
        """ :type datastore_id: str """
        self._get_response_data('delete', '/datastore/%s' % datastore_id)

    def patch_action(self, action, **data_properties):
        """ :type action: dart.model.action.Action
            :rtype: dart.model.action.Action """
        p = self._get_patch(action, data_properties)
        return self._request('patch', '/action/%s' % action.id, data=p.patch, model_class=Action)

    @staticmethod
    def _get_patch(model, data_properties):
        updated_model_dict = model.to_dict()
        for k, v in data_properties.iteritems():
            updated_model_dict['data'][k] = v
        return jsonpatch.make_patch(model.to_dict(), updated_model_dict)

    def save_actions(self, actions, datastore_id=None, workflow_id=None):
        """ :type actions: list[dart.model.action.Action]
            :rtype: list[dart.model.action.Action] """
        # the ^ operator on two bool values is an xor
        assert bool(datastore_id) ^ bool(workflow_id), 'please pass either datastore_id or workflow_id'
        for a in actions:
            assert not a.id, 'updating an action is not supported - action has id: %s' % a.id

        data = [a.to_dict() for a in actions]
        if datastore_id:
            return self._request_list('post', '/datastore/%s/action' % datastore_id, data=data, model_class=Action)
        if workflow_id:
            return self._request_list('post', '/workflow/%s/action' % workflow_id, data=data, model_class=Action)

    def await_action_completion(self, action_id, timeout_seconds=2):
        """ :type action_id: str
            :rtype: dart.model.action.Action """
        finished_states = [ActionState.COMPLETED, ActionState.FAILED]
        while True:
            action = self.get_action(action_id)
            if action.data.state in finished_states:
                return action
            time.sleep(timeout_seconds)

    def get_action(self, action_id):
        """ :type action_id: str
            :rtype: dart.model.action.Action """
        return self._request('get', '/action/%s' % action_id, model_class=Action)

    def find_actions(self, filters=None):
        """ :type filters: list[dart.model.query.Filter]
            :rtype: list[dart.model.action.Action] """
        limit = 20
        offset = 0
        while True:
            fs_string = json.dumps([' '.join([f.key, f.operator, f.value]) for f in filters or []])
            params = {'limit': limit, 'offset': offset, 'filters': fs_string}
            results = self._request_list('get', '/action', params=params, model_class=Action)
            if len(results) == 0:
                break
            for e in results:
                yield e
            offset += limit

    def get_actions(self, datastore_id=None, workflow_id=None):
        """ :type datastore_id: str
            :type workflow_id: str
            :rtype: list[dart.model.action.Action] """
        assert datastore_id or workflow_id, 'datastore_id and/or workflow_id must be provided'
        filters = []
        if datastore_id:
            filters.append(Filter('datastore_id', Operator.EQ, datastore_id))
        if workflow_id:
            filters.append(Filter('workflow_id', Operator.EQ, workflow_id))
        return self.find_actions(filters)

    def delete_action(self, action_id):
        """ :type action_id: str """
        self._get_response_data('delete', '/action/%s' % action_id)

    def save_workflow(self, workflow, datastore_id=None):
        """ :type workflow: dart.model.workflow.Workflow
            :type datastore_id: str
            :rtype: dart.model.workflow.Workflow """
        if workflow.id:
            return self._request('put', '/workflow/%s' % workflow.id, data=workflow.to_dict(), model_class=Workflow)
        datastore_id = datastore_id or workflow.data.datastore_id
        assert datastore_id, 'datastore_id must be provided to save a new workflow'
        return self._request('post', '/datastore/%s/workflow' % datastore_id, data=workflow.to_dict(), model_class=Workflow)

    def patch_workflow(self, workflow, **data_properties):
        """ :type workflow: dart.model.workflow.Workflow
            :rtype: dart.model.workflow.Workflow """
        p = self._get_patch(workflow, data_properties)
        return self._request('patch', '/workflow/%s' % workflow.id, data=p.patch, model_class=Workflow)

    def get_workflow(self, workflow_id):
        """ :type workflow_id: str
            :rtype: dart.model.workflow.Workflow """
        return self._request('get', '/workflow/%s' % workflow_id, model_class=Workflow)

    def manually_trigger_workflow(self, workflow_id):
        """ :type workflow_id: str """
        self._get_response_data('post', '/workflow/%s/do-manual-trigger' % workflow_id)

    def await_workflow_completion(self, workflow_id, num_instances=1, timeout_seconds=2):
        """ :type workflow_id: str
            :type num_instances: int
            :rtype: list[dart.model.workflow.WorkflowInstance] """
        finished_states = [WorkflowInstanceState.COMPLETED, WorkflowInstanceState.FAILED]
        while True:
            wfis = self.get_workflow_instances(workflow_id)
            num_finished = sum([1 for wfi in wfis if wfi.data.state in finished_states])
            if num_finished >= num_instances:
                return wfis
            time.sleep(timeout_seconds)

    def get_workflow_instances(self, workflow_id):
        """ :type workflow_id: str
            :rtype: list[dart.model.workflow.WorkflowInstance] """
        return self._request_list('get', '/workflow/%s/instance' % workflow_id, model_class=WorkflowInstance)

    def delete_workflow(self, workflow_id):
        """ :type workflow_id: str """
        self._get_response_data('delete', '/workflow/%s' % workflow_id)

    def delete_workflow_instances(self, workflow_id):
        """ :type workflow_id: str """
        self._get_response_data('delete', '/workflow/%s/instance' % workflow_id)

    def save_subscription(self, subscription, dataset_id=None):
        """ :type subscription: dart.model.subscription.Subscription
            :type dataset_id: str
            :rtype: dart.model.subscription.Subscription """
        if subscription.id:
            return self._request('put', '/subscription/%s' % subscription.id, data=subscription.to_dict(), model_class=Subscription)
        dataset_id = dataset_id or subscription.data.dataset_id
        assert dataset_id, 'dataset_id must be provided to save a new subscription'
        return self._request('post', '/dataset/%s/subscription' % subscription.data.dataset_id, data=subscription.to_dict(), model_class=Subscription)

    def patch_subscription(self, subscription, **data_properties):
        """ :type subscription: dart.model.subscription.Subscription
            :rtype: dart.model.subscription.Subscription """
        p = self._get_patch(subscription, data_properties)
        return self._request('patch', '/subscription/%s' % subscription.id, data=p.patch, model_class=Subscription)

    def await_subscription_generation(self, subscription_id, timeout_seconds=2):
        """ :type subscription_id: str
            :rtype: dart.model.subscription.Subscription """
        while True:
            subscription = self.get_subscription(subscription_id)
            if subscription.data.state not in [SubscriptionState.QUEUED, SubscriptionState.GENERATING]:
                return subscription
            time.sleep(timeout_seconds)

    def get_subscription(self, subscription_id):
        """ :type subscription_id: str
            :rtype: dart.model.subscription.Subscription """
        return self._request('get', '/subscription/%s' % subscription_id, model_class=Subscription)

    def get_subscription_elements(self, action_id):
        """ :type action_id: str
            :rtype: list[dart.model.subscription.SubscriptionElement] """
        limit = 10000
        offset = 0
        while True:
            params = {'limit': limit, 'offset': offset}
            results = self._request_list('get', '/action/%s/subscription/elements' % action_id, params=params, model_class=SubscriptionElement)
            if len(results) == 0:
                break
            for e in results:
                yield e
            offset += limit

    def find_subscription_elements(self, subscription_id, state=None, processed_after_s3_path=None):
        """ :type subscription_id: str
            :type state: str
            :type processed_after_s3_path: str
            :rtype: list[dart.model.subscription.SubscriptionElement] """
        limit = 10000
        offset = 0
        while True:
            params = {
                'limit': limit,
                'offset': offset,
                'state': state,
                'processed_after_s3_path': processed_after_s3_path if processed_after_s3_path else None
            }
            results = self._request_list('get', '/subscription/%s/elements' % subscription_id, params=params, model_class=SubscriptionElement)
            if len(results) == 0:
                break
            for e in results:
                yield e
            offset += limit

    def get_subscription_element_stats(self, subscription_id):
        """ :type subscription_id: str
            :rtype: list[dart.model.subscription.SubscriptionElementStats] """
        return self._request_list('get', '/subscription/%s/element_stats' % subscription_id, model_class=SubscriptionElementStats)

    def delete_subscription(self, subscription_id):
        """ :type subscription_id: str """
        self._get_response_data('delete', '/subscription/%s' % subscription_id)

    def save_trigger(self, trigger):
        """ :type trigger: dart.model.trigger.Trigger
            :rtype: dart.model.trigger.Trigger """
        return self._request('post', '/trigger', data=trigger.to_dict(), model_class=Trigger)

    def patch_trigger(self, trigger, **data_properties):
        """ :type trigger: dart.model.trigger.Trigger
            :rtype: dart.model.trigger.Trigger """
        p = self._get_patch(trigger, data_properties)
        return self._request('patch', '/trigger/%s' % trigger.id, data=p.patch, model_class=Trigger)

    def get_trigger(self, trigger_id):
        """ :type trigger_id: str
            :rtype: dart.model.trigger.Trigger """
        return self._request('get', '/trigger/%s' % trigger_id, model_class=Trigger)

    def get_trigger_types(self):
        """ :rtype: dart.model.trigger.TriggerType """
        return self._request_list('get', '/trigger_type', model_class=TriggerType)

    def delete_trigger(self, trigger_id):
        """ :type trigger_id: str """
        self._get_response_data('delete', '/trigger/%s' % trigger_id)

    def save_event(self, event):
        """ :type event: dart.model.event.Event
            :rtype: dart.model.event.Event """
        if event.id:
            return self._request('put', '/event/%s' % event.id, data=event.to_dict(), model_class=Event)
        return self._request('post', '/event', data=event.to_dict(), model_class=Event)

    def patch_event(self, event, **data_properties):
        """ :type event: dart.model.event.Event
            :rtype: dart.model.event.Event """
        p = self._get_patch(event, data_properties)
        return self._request('patch', '/event/%s' % event.id, data=p.patch, model_class=Event)

    def get_event(self, event_id):
        """ :type event_id: str
            :rtype: dart.model.event.Event """
        return self._request('get', '/event/%s' % event_id, model_class=Event)

    def delete_event(self, event_id):
        """ :type event_id: str """
        self._get_response_data('delete', '/event/%s' % event_id)

    def get_entity_graph(self, entity_type, entity_id):
        """ :type entity_type: str
            :type entity_id: str
            :rtype: dart.model.graph.Graph """
        return self._request('get', '/graph/%s/%s' % (entity_type, entity_id), model_class=Graph)

    def _get_response_data(self, method, url_prefix, data=None, params=None):
        basic_auth_signature = encode(self._credential, self._secret)
        headers = {
            'Authorization': basic_auth_signature
        }
        response = requests.request(method, self._base_url + '/' + url_prefix.lstrip('/'), headers=headers, json=data, params=params, verify=False)
        try:
            data = response.json()
            if data['results'] == 'ERROR':
                raise
            return data['results']
        except:
            raise DartRequestException(response)

    def _request(self, method, url_prefix=None, data=None, params=None, model_class=None):
        response_data = self._get_response_data(method, url_prefix, data, params)
        return model_class.from_dict(response_data)

    def _request_list(self, method, url_prefix=None, data=None, params=None, model_class=None):
        elements = self._get_response_data(method, url_prefix, data, params)
        return [model_class.from_dict(e) for e in elements]
