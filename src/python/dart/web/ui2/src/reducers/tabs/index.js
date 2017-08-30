import { SELECT_ENTITY, ADD_TAB, SELECT_TAB } from 'actions/';
import tab, * as fromTab from './tab'

export const getSelected = state => state.tabs[state.selected];
export const getCurrentIndex = state => state.selected;
export const getTabs = state => state.tabs;

export default (
    state = {
        tabs: [ tab(undefined, {}) ],
        selected: 0
    },
    action
) => {
    switch (action.type) {
        case SELECT_TAB:
            return {
                ...state,
                selected: action.index
            };
        case ADD_TAB:
            return {
                ...state,
                tabs: [
                    ...state.tabs,
                    tab(undefined, action)
                ]
            };
        case SELECT_ENTITY:
            return {
                ...state,
                tabs: [
                    ...state.tabs.slice(0, state.selected),
                    tab(state.tabs[state.selected], action),
                    ...state.tabs.slice(state.selected + 1)
                ]
            };
        default:
            return state;
    }
};
