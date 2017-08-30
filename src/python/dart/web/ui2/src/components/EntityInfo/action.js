import React, { Component } from 'react';
import { connect } from 'react-redux';

import { selectEntity, fetchEntity } from 'actions/';
import EntityInfo from './entity';

class ActionInfo extends Component {

    onWorkflowClick(e) {
        e.preventDefault();
        const entity = {
            type: 'workflow',
            id: this.props.data.data.workflow_id
        };

        this.props.fetchEntity(entity);
        this.props.selectEntity(entity);
    }

    render = () => <EntityInfo
        entity={this.props.entity}
        data={this.props.data}
        extraFields={
            <div>
                WORKFLOW: <a href="#" onClick={this.onWorkflowClick.bind(this)}>{this.props.data.data.workflow_id}</a>
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
)(ActionInfo);
