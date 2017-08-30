import { combineReducers } from 'redux';
import zipObject from 'lodash/zipObject';
import map from 'lodash/map';
import axios from 'axios';

const getSchemaState = (state, entity, entityData) => {
    state = state[entity.type];
    if (!entityData)
        return schema(undefined, {});

    switch (entity.type) {
        case 'datastore':
            return schema(state[entityData.data.engine_name], {});
        case 'action':
            state = state[entityData.data.engine_name];
            if (!state)
                return schema(undefined, {});

            return schema(state[entityData.data.action_type_name], {});
        case 'workflow_instance':
            return 'workflow/instance';
        case 'trigger':
            return state[entityData.data.trigger_type_name];
        default:
            return state;
    }
};

export const getSchema = (state, entity, entityData) => getSchemaState(state, entity, entityData).data;
export const getSchemaIsFetching = (state, entity, entityData) => getSchemaState(state, entity, entityData).isFetching;
export const getSchemaErrorMessage = (state, entity, entityData) => getSchemaState(state, entity, entityData).errorMessage;

const FETCH_SCHEMA_REQUEST = 'FETCH_SCHEMA_REQUEST';
const fetchSchemaRequest = (entity, entityData) => ({
    type: FETCH_SCHEMA_REQUEST,
    entity,
    entityData
});

const FETCH_SCHEMA_SUCCESS = 'FETCH_SCHEMA_SUCCESS';
const fetchSchemaSuccess = (entity, entityData, response) => ({
    type: FETCH_SCHEMA_SUCCESS,
    entity,
    entityData,
    response
});

const FETCH_SCHEMA_FAILURE = 'FETCH_SCHEMA_FAILURE';
const fetchSchemaFailure = (entity, entityData, error) => ({
    type: FETCH_SCHEMA_FAILURE,
    entity,
    entityData,
    message: error.message || 'Something went wrong.'
});

const getEndpoint = (entity, entityData) => {
    switch (entity.type) {
        case 'datastore':
            return `engine/${entityData.data.engine_name}/datastore`;
        case 'action':
            return `action/${entityData.data.action_type_name}?engine_name=${entityData.data.engine_name}`;
        case 'workflow_instance':
            return 'workflow/instance';
        case 'trigger':
            return `trigger?trigger_type_name=${entityData.data.trigger_type_name}`;
        default:
            return entity.type;
    }
};

export const fetchSchema = (entity, entityData) => (dispatch, getState) => {
    if (getSchemaIsFetching(getState(), entity))
        return Promise.resolve();

    dispatch(fetchSchemaRequest(entity, entityData));

    const endpoint = `/api/1/schema/${getEndpoint(entity, entityData)}`;
    return axios.get(endpoint).then(
        response => { dispatch(fetchSchemaSuccess(entity, entityData, response)); },
        error => { dispatch(fetchSchemaFailure(entity, entityData, error)); }
    );
};

const entity_types = [
    'dataset',
    'datastore',
    'action',
    'workflow',
    'workflow_instance',
    'subscription',
    'trigger'
];

const schema = (
    state = {
        isFetching: false,
        errorMessage: null,
        data: {}
    },
    action
) => {
    switch (action.type) {
        case FETCH_SCHEMA_REQUEST:
            return {
                ...state,
                isFetching: true,
                errorMessage: null
            };
        case FETCH_SCHEMA_SUCCESS:
            return {
                ...state,
                isFetching: false,
                errorMessage: null,
                data: action.response.data.results
            };
        case FETCH_SCHEMA_FAILURE:
            return {
                ...state,
                isFetching: false,
                errorMessage: action.errorMessage
            };
        default:
            return state;
    }
};

const entityTypeSchema = (type, reducer = schema) => (state, action) => {
    if (!action.entity || action.entity.type !== type)
        return reducer(state, {});

    return reducer(state, action);
};

const engineAction = (state = {}, action) => {
    const action_type = action.entityData.data.action_type_name;
    return {
        ...state,
        [action_type]: schema(state[action_type], action)
    };
};

const action = (state = {}, action) => {
    if (!action.entityData)
        return state;

    const engine = action.entityData.data.engine_name;
    return {
        ...state,
        [engine]: engineAction(state[engine], action)
    };
};

const datastore = (state = {}, action) => {
    if (!action.entityData)
        return state;

    const engine = action.entityData.data.engine_name;
    return {
        ...state,
        [engine]: schema(state[engine], action)
    };
};

const trigger = (state = {}, action) => {
    if (!action.entityData)
        return state;

    const trigger_type = action.entityData.data.trigger_type_name;
    return {
        ...state,
        [trigger_type]: schema(state[trigger_type], action)
    };
};

export default combineReducers({
    dataset: entityTypeSchema('dataset'),
    datastore: entityTypeSchema('datastore', datastore),
    action: entityTypeSchema('action', action),
    workflow: entityTypeSchema('workflow'),
    workflow_instance: entityTypeSchema('workflow_instance'),
    subscription: entityTypeSchema('subscription'),
    trigger: entityTypeSchema('trigger', trigger)
});
