import React, { Component, PropTypes } from 'react';
import { connect } from 'react-redux';
import Toggle from 'material-ui/Toggle';

import { getGraph, getGraphIsFetching, getGraphErrorMessage } from 'reducers/';
import { getSelectedEntityData, getSelectedEntityIsFetching } from 'api/';

class Pane extends Component {

    render() {
        return (
            <div style={{ height: '100%', width: '100%', overflowY: 'scroll' }} >
                {this.props.data.nodes.map(n => <Toggle
                    key={`${n.entity_type}-${n.entity_id}`}
                    label={`${n.entity_id}   ${n.name}`}
                    labelPosition="right"
                />)}
                {this.props.data.nodes.map(n => <Toggle
                    key={`${n.entity_type}-${n.entity_id}`}
                    label={`${n.entity_id}   ${n.name}`}
                    labelPosition="right"
                />)}
                {this.props.data.nodes.map(n => <Toggle
                    key={`${n.entity_type}-${n.entity_id}`}
                    label={`${n.entity_id}   ${n.name}`}
                    labelPosition="right"
                />)}
                {this.props.data.nodes.map(n => <Toggle
                    key={`${n.entity_type}-${n.entity_id}`}
                    label={`${n.entity_id}   ${n.name}`}
                    labelPosition="right"
                />)}
                {this.props.data.nodes.map(n => <Toggle
                    key={`${n.entity_type}-${n.entity_id}`}
                    label={`${n.entity_id}   ${n.name}`}
                    labelPosition="right"
                />)}
                {this.props.data.nodes.map(n => <Toggle
                    key={`${n.entity_type}-${n.entity_id}`}
                    label={`${n.entity_id}   ${n.name}`}
                    labelPosition="right"
                />)}
                {this.props.data.nodes.map(n => <Toggle
                    key={`${n.entity_type}-${n.entity_id}`}
                    label={`${n.entity_id}   ${n.name}`}
                    labelPosition="right"
                />)}

            </div>
        );
    }
}

Pane.propTypes = {
};

export default connect(
    (state, ownProps) => ({
        isFetching: getGraphIsFetching(state, ownProps.entity),
        errorMessage: getGraphErrorMessage(state, ownProps.entity),
        data: getGraph(state, ownProps.entity),
    })
)(Pane);
