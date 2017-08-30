import React, { Component } from 'react';
import { connect } from 'react-redux';
import TextField from 'material-ui/TextField';
import DropDownMenu from 'material-ui/DropDownMenu';
import MenuItem from 'material-ui/MenuItem';

import { selectEntity, fetchEntity, updateEntity } from 'actions/';

const entityStates = {
    workflow: ['ACTIVE', 'INACTIVE'],
    datastore: ['ACTIVE', 'INACTIVE']
};

class EntityInfo extends Component {

    getStateComponent() {
        const { type } = this.props.entity;
        const state = this.props.data.data.state;

        if (type in entityStates)
            return <DropDownMenu
                value={state}
                onChange={(e, i, v) => {
                    e.preventDefault();
                    this.props.updateEntity(this.props.entity, 'data.state', v);
                }}
            >
                { entityStates[type].map(s => <MenuItem key={s} value={s} primaryText={s} />) }
            </DropDownMenu>;

        return this.props.data.data.state;
    }

    render = () => <div>
        {this.props.entity.type.toUpperCase()} {this.props.data.id}

        <br />

        STATE: {this.getStateComponent()}

        <br />

        NAME: <TextField
            defaultValue={this.props.data.data.name}
            name="name"
            onChange={(e, v) => {
                e.preventDefault();
                this.props.updateEntity(this.props.entity, 'data.name', v);
            }}
        />

        {this.props.extraFields}
    </div>;
}

export default connect(
    (state,) => ({

    }), {
        selectEntity,
        fetchEntity,
        updateEntity
    }
)(EntityInfo);
