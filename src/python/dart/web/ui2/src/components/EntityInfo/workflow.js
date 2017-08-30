import React, { Component } from 'react';
import { connect } from 'react-redux';

import { selectEntity, fetchEntity } from 'actions/';
import EntityInfo from './entity';

class WorkflowInfo extends Component {

    onDatastoreClick(e) {
        e.preventDefault();
        const entity = {
            type: 'datastore',
            id: this.props.data.data.datastore_id
        };

        this.props.fetchEntity(entity);
        this.props.selectEntity(entity);
    }

    render = () => <EntityInfo
        entity={this.props.entity}
        data={this.props.data}
        extraFields={
            <div>
                DATASTORE: <a href="#" onClick={this.onDatastoreClick.bind(this)}>{this.props.data.data.datastore_id}</a>
            </div>
        }
    />;
}

export default connect(
    (state,) => ({

    }), {
        selectEntity,
        fetchEntity
    }
)(WorkflowInfo);
