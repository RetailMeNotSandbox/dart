export const SELECT_ENTITY = 'SELECT_ENTITY';
export const selectEntity = entity => ({
    type: SELECT_ENTITY,
    entity,
});

export const SELECT_TAB = 'SELECT_TAB';
export const selectTab = index => ({
    type: SELECT_TAB,
    index,
});

export const ADD_TAB = 'ADD_TAB';
export const addTab = () => ({
    type: ADD_TAB
});

export const UPDATE_ENTITY = 'UPDATE_ENTITY';
export const updateEntity = (entity, path, value) => ({
    type: UPDATE_ENTITY,
    entity,
    path,
    value
});

import * as fromApi from 'api/';
export const fetchGraph = entity => (dispatch, getState) => fromApi.fetchGraph(entity)(dispatch, () => getState().api);
export const fetchSchema = entity => (dispatch, getState) => fromApi.fetchSchema(entity)(dispatch, () => getState().api);
export const fetchEntity = (entity, entityData) => (dispatch, getState) => fromApi.fetchEntity(entity, entityData)(dispatch, () => getState().api);
export const search = query => (dispatch, getState) => fromApi.search(query)(dispatch, () => getState().api);