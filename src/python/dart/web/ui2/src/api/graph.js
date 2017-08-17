import { combineReducers } from 'redux';
import zipObject from 'lodash/zipObject'
import map from 'lodash/map'
import axios from 'axios';


const getGraphState = (state, entity) => graph(state[entity.type][entity.id], {}) || {};
export const getGraph = (state, entity) => getGraphState(state, entity).data;
export const getGraphIsFetching = (state, entity) => getGraphState(state, entity).isFetching;
export const getGraphErrorMessage = (state, entity) => getGraphState(state, entity).errorMessage;


const FETCH_GRAPH_REQUEST = 'FETCH_GRAPH_REQUEST';
const fetchGraphRequest = (entity) => ({
    type: FETCH_GRAPH_REQUEST,
    entity
});

const FETCH_GRAPH_SUCCESS = 'FETCH_GRAPH_SUCCESS';
const fetchGraphSuccess = (entity, response) => ({
    type: FETCH_GRAPH_SUCCESS,
    entity,
    response
});

const FETCH_GRAPH_FAILURE = 'FETCH_GRAPH_FAILURE';
const fetchGraphFailure = (entity, error) => ({
    type: FETCH_GRAPH_FAILURE,
    entity,
    message: error.message || 'Something went wrong.'
});

export const fetchGraph = entity => (dispatch, getState) => {
    if (getGraphIsFetching(getState(), entity))
        return Promise.resolve();

    dispatch(fetchGraphRequest(entity));

    const { type, id } = entity;
    return axios.get('/api/1/graph/' + type + '/' + id).then(
        response => { dispatch(fetchGraphSuccess(entity, response)); },
        error => { dispatch(fetchGraphFailure(entity, error)); }
    );
};

export const actions = { fetchGraph };

const entity_types = [
    'dataset',
    'datastore',
    'action',
    'workflow',
    'workflow_instance',
    'subscription',
    'trigger'
];

function graph(
    state = {
        isFetching: false,
        errorMessage: null,
        data: {
            nodes: [],
            edges: []
        }
    },
    action
) {
    switch (action.type) {
        case FETCH_GRAPH_REQUEST:
            return {
                ...state,
                isFetching: true,
                errorMessage: null
            };
        case FETCH_GRAPH_SUCCESS:
            return {
                ...state,
                isFetching: false,
                errorMessage: null,
                data: action.response.data.results
            };
        case FETCH_GRAPH_FAILURE:
            return {
                ...state,
                isFetching: false,
                errorMessage: action.errorMessage
            };
        default:
            return state;
    }
}

export default combineReducers(
    zipObject(entity_types, map(entity_types, type => (state = {}, action) => {
        switch (action.type) {
            case FETCH_GRAPH_REQUEST:
            case FETCH_GRAPH_SUCCESS:
            case FETCH_GRAPH_FAILURE:
                if (action.entity.type !== type)
                    return state;

                const id = action.entity.id;
                return {
                    ...state,
                    [id]: graph(state[id], action)
                };
            default:
                return state;
        }
    }))
);
