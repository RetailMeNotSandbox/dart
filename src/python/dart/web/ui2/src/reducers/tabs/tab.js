import { v4 } from 'node-uuid';

import { SELECT_ENTITY } from 'actions/';

export default (
    state = {
        id: v4(),
        entity: null,
        updates: {}
    },
    action
) => {
    switch (action.type) {
        case SELECT_ENTITY:
            return {
                ...state,
                entity: action.entity
            };
        default:
            return state;
    }
};
