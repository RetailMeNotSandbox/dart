import isEqual from 'lodash/isEqual';

import api, * as fromApi from 'api/';
import tabs, * as fromTabs from './tabs/';

export const getTabs = state => fromTabs.getTabs(state.tabs).map(({ id, entity }) => {
    let entityData = fromApi.getEntity(state.api, entity);
    return {
        id,
        entity,
        name: (entityData && !isEqual(entityData, {})) ? entityData.data.name : id,
        data: entityData
    };
});

export const getSelectedTabIndex = state => fromTabs.getCurrentIndex(state.tabs);

export const getGraph = (state, entity) => fromApi.getGraph(state.api, entity);
export const getGraphIsFetching = (state, entity) => fromApi.getGraphIsFetching(state.api, entity);
export const getGraphErrorMessage = (state, entity) => fromApi.getGraphErrorMessage(state.api, entity);

export const getEntity = (state, entity) => fromApi.getEntity(state.api, entity);
export const getEntityIsFetching = (state, entity) => fromApi.getEntityIsFetching(state.api, entity);
export const getEntityErrorMessage = (state, entity) => fromApi.getEntityErrorMessage(state.api, entity);

export const getSearchResults = state => fromApi.getSearchResults(state.api);
export const getSearchQuery = state => fromApi.getSearchQuery(state.api);
export const getSearchIsFetching = state => {
    console.log(state);
    return fromApi.getSearchIsFetching(state.api);
};

export const getSchema = (state, entity) => {
    const entityData = getEntity(state, entity);
    if (!entityData || isEqual(entityData, {}))
        return null;

    return fromApi.getSchema(state.api, entity, entityData);
};

export const getSchemaIsFetching = (state, entity, entityData) => fromApi.getSchemaIsFetching(state.api, entity, entityData);
export const getSchemaErrorMessage = (state, entity, entityData) => fromApi.getSchemaErrorMessage(state.api, entity, entityData);

export const getSelectedTab = state => fromTabs.getSelected(state.tabs);
export const getSelectedEntity = state => getSelectedTab(state).entity;


export default {
    api,
    tabs
};
