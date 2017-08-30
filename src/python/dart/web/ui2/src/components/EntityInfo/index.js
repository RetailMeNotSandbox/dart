import React, { Component, PropTypes } from 'react';
import { connect } from 'react-redux';
import Tab from 'react-toolbox/lib/tabs/Tab';
import Tabs from 'react-toolbox/lib/tabs/Tabs';
import isEqual from 'lodash/isEqual';
import { SchemaForm } from 'react-schema-form';
import axios from 'axios';
import { Scrollbars } from 'react-custom-scrollbars';

import { getTabs, getSelectedTabIndex, getSchema, getEntity } from 'reducers/';
import { addTab, selectTab, fetchEntity } from 'actions/';

import action from './action';
import workflow from './workflow';
import datastore from './datastore'

class EntityInfo extends Component {

    entityComponents = {
        workflow,
        action,
        datastore
    };

    defaultContent() {
        if (!this.props.schema || !this.props.entityData || isEqual(this.props.schema, {}))
            return <div></div>;

        const form = ['*'];

        return (
            <div style={{ height: '100%', width: '100%', overflow: 'scroll' }} >
                <SchemaForm
                    schema={this.props.schema}
                    form={form}
                    model={this.props.entityData}
                    onModelChange={(path, value) => { console.log(path, value, this.props.entityData); }}
                    style={{ height: '100%', width: '100%', overflow: 'scroll' }}
                />
            </div>
        );
    }

    render() {
        if (!this.props.entity || isEqual(this.props.entityData, {}))
            return <div></div>;

        const EntityComponent = this.entityComponents[this.props.entity.type];
        if (EntityComponent)
            return <EntityComponent entity={this.props.entity} data={this.props.entityData} />;

        return this.defaultContent();
    }
}

EntityInfo.propTypes = {
};

export default connect(
    (state, props) => ({
        tabs: getTabs(state),
        selected: getSelectedTabIndex(state),
        schema: getSchema(state, props.entity),
        entityData: getEntity(state, props.entity)
    }),
    {
        selectTab,
        addTab,
        fetchEntity
    }
)(EntityInfo);
