const SELECT_ENTITY = 'SELECT_ENTITY';
export const selectEntity = entity => ({
    type: SELECT_ENTITY,
    entity,
});

export default function selected(state = null, action) {
    switch (action.type) {
        case SELECT_ENTITY:
            return action.entity;
        default:
            return state;
    }
}

export const getSelectedEntityType = state => state.type;
export const getSelectedEntityId = state => state.id;
export const getSelectedEntity = state => state;
