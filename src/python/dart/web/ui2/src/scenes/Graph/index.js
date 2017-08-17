import React, { Component, PropTypes } from 'react';
import { connect } from 'react-redux';
import { withRouter } from 'react-router'
import SplitterLayout from 'react-panelgroup';
import isEqual from 'lodash/isEqual';

import Graph from 'components/Graph'
import InfoPane from 'components/InfoPane';


class GraphScene extends Component {

    render() {
        return (
            <SplitterLayout style={{width: '100%', height: '100%'}} >
                <Graph
                    entity={this.props.entity}
                    style={{width: '100%', height: '100%', 'backgroundColor': 'purple'}}
                />
                <InfoPane />
            </SplitterLayout>
        );
    }
}

GraphScene.propTypes = {
    entity: PropTypes.shape({
        type: PropTypes.string.isRequired,
        id: PropTypes.string.isRequired
    }).isRequired
};

export default withRouter(connect(
    (state, { match }) => {
        const { type, id} = match.params;
        const entity = { type, id };
        return {
            entity: entity
        };
    }
)(GraphScene));
