import { combineReducers } from 'redux';

import graphsReducer, * as fromGraphs from './graph';
export const getGraph = (state, entity) => fromGraphs.getGraph(state.graphs, entity);
export const getGraphIsFetching = (state, entity) => fromGraphs.getGraphIsFetching(state.graphs, entity);
export const getGraphErrorMessage = (state, entity) => fromGraphs.getGraphErrorMessage(state.graphs, entity);
export const fetchGraph = entity => (dispatch, getState) => fromGraphs.fetchGraph(entity)(dispatch, () => getState().graphs);

import schemasReducer, * as fromSchemas from './schema';
export const getSchema = (state, entity, entityData) => fromSchemas.getSchema(state.schemas, entity, entityData);
export const getSchemaIsFetching = (state, entity, entityData) => fromSchemas.getSchemaIsFetching(state.schemas, entity, entityData);
export const getSchemaErrorMessage = (state, entity, entityData) => fromSchemas.getSchemaErrorMessage(state.schemas, entity, entityData);
export const fetchSchema = (entity, entityData) => (dispatch, getState) => fromSchemas.fetchSchema(entity, entityData)(dispatch, () => getState().schemas);

import entitiesReducer, * as fromEntities from './entity';
export const getEntity = (state, entity) => fromEntities.getEntity(state.entities, entity);
export const getEntityIsFetching = (state, entity) => fromEntities.getEntityIsFetching(state.entities, entity);
export const getEntityErrorMessage = (state, entity) => fromEntities.getEntityErrorMessage(state.entities, entity);
export const fetchEntity = entity => (dispatch, getState) => fromEntities.fetchEntity(entity)(dispatch, () => getState().entities).then(
    response => { fetchSchema(entity, response.data.results)(dispatch, getState); }
);

import searchReducer, * as fromSearch from './search';
export const getSearchResults = state => fromSearch.getResults(state.search);
export const getSearchQuery = state => fromSearch.getQuery(state.search);
export const getSearchIsFetching = state => fromSearch.getIsFetching(state.search);
export const search = query => (dispatch, getState) => fromSearch.search(query)(dispatch, () => getState().search);

export default combineReducers({
    graphs: graphsReducer,
    schemas: schemasReducer,
    entities: entitiesReducer,
    search: searchReducer
});
