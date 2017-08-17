import { combineReducers } from 'redux';

import graphs, * as fromGraphs from './graph';
export const getGraph = (state, entity) => fromGraphs.getGraph(state.graphs, entity);
export const getGraphIsFetching = (state, entity) => fromGraphs.getGraphIsFetching(state.graphs, entity);
export const getGraphErrorMessage = (state, entity) => fromGraphs.getGraphErrorMessage(state.graphs, entity);
export const fetchGraph = entity => (dispatch, getState) => fromGraphs.fetchGraph(entity)(dispatch, () => getState().graphs);

import entities, * as fromEntities from './entity';
export const getEntity = (state, entity) => fromEntities.getEntity(state.entities, entity);
export const getEntityIsFetching = (state, entity) => fromEntities.getEntityIsFetching(state.entities, entity);
export const getEntityErrorMessage = (state, entity) => fromEntities.getEntityErrorMessage(state.entities, entity);
export const fetchEntity = entity => (dispatch, getState) => fromEntities.fetchEntity(entity)(dispatch, () => getState().entities);

import selected, * as fromSelected from './selected'
export const getSelectedEntity = state => fromSelected.getSelectedEntity(state.selected);
export const selectEntity = entity => (dispatch, getState) => {
    fetchEntity(entity)(dispatch, getState);
    dispatch(fromSelected.selectEntity(entity));
};

export const getSelectedEntityData = state => getEntity(state, getSelectedEntity(state));
export const getSelectedEntityIsFetching = state => getEntityIsFetching(state, getSelectedEntity(state));


export const reducer = combineReducers({
    graphs,
    entities,
    selected
});
