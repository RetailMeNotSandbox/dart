import React, { Component, PropTypes } from 'react';
import { connect } from 'react-redux';
import { withRouter } from 'react-router';
import SplitterLayout from 'react-panelgroup';

import Graph from 'components/Graph'
import InfoPane from 'components/InfoPane';

class GraphScene extends Component {

    render() {
        return (
            <SplitterLayout borderColor="black" >
                <Graph entity={this.props.entity} />
                <InfoPane entity={this.props.entity} />
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
