import { combineReducers } from 'redux';
import zipObject from 'lodash/zipObject'
import map from 'lodash/map';
import set from 'lodash/set';
import axios from 'axios';

import { UPDATE_ENTITY } from 'actions';

const getEntityState = (state, e) => entity(e ? state[e.type][e.id] : undefined, {});
export const getEntity = (state, e) => getEntityState(state, e).data;
export const getEntityIsFetching = (state, e) => getEntityState(state, e).isFetching;
export const getEntityErrorMessage = (state, e) => getEntityState(state, e).errorMessage;

const FETCH_ENTITY_REQUEST = 'FETCH_ENTITY_REQUEST';
const fetchEntityRequest = (entity) => ({
    type: FETCH_ENTITY_REQUEST,
    entity
});

const FETCH_ENTITY_SUCCESS = 'FETCH_ENTITY_SUCCESS';
const fetchEntitySuccess = (entity, response) => ({
    type: FETCH_ENTITY_SUCCESS,
    entity,
    response
});

const FETCH_ENTITY_FAILURE = 'FETCH_ENTITY_FAILURE';
const fetchEntityFailure = (entity, error) => ({
    type: FETCH_ENTITY_FAILURE,
    entity,
    message: error.message || 'Something went wrong.'
});

const getEntityEndpoint = t => {
    switch (t) {
        case 'workflow_instance':
            return 'workflow/instance';
        default:
            return t
    }
};

export const fetchEntity = entity => (dispatch, getState) => {
    if (getEntityIsFetching(getState(), entity))
        return Promise.resolve();

    dispatch(fetchEntityRequest(entity));

    const { type, id } = entity;
    const endpoint = `/api/1/${getEntityEndpoint(type)}/${id}`;
    return axios.get(endpoint).then(
        response => {
            dispatch(fetchEntitySuccess(entity, response));
            return response;
        }, error => {
            dispatch(fetchEntityFailure(entity, error));
            return error;
        }
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

function entity(
    state = {
        isFetching: false,
        errorMessage: null,
        data: {}
    },
    action
) {
    switch (action.type) {
        case FETCH_ENTITY_REQUEST:
            return {
                ...state,
                isFetching: true,
                errorMessage: null
            };
        case FETCH_ENTITY_SUCCESS:
            return {
                ...state,
                isFetching: false,
                errorMessage: null,
                data: action.response.data.results
            };
        case FETCH_ENTITY_FAILURE:
            return {
                ...state,
                isFetching: false,
                errorMessage: action.errorMessage
            };
        case UPDATE_ENTITY:
            return {
                ...state,
                data: set({...state.data}, action.path, action.value)
            };
        default:
            return state;
    }
}

export default combineReducers(
    zipObject(entity_types, map(entity_types, type => (state = {}, action) => {
        if (!action.entity || action.entity.type !== type)
            return state;

        const id = action.entity.id;
        return {
            ...state,
            [id]: entity(state[id], action)
        };
    }))
);
