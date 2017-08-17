import React, { Component, PropTypes } from 'react';
import { connect } from 'react-redux';

import { getSelectedEntityData, getSelectedEntityIsFetching } from 'api/';

class Pane extends Component {

    getContent() {
        const { isFetching, errorMessage, data } = this.props;

        if (isFetching || !data.data)
            return <div style={{width: '100%', height: '100%'}} >Loading...</div>;
        if (errorMessage)
            return <div style={{width: '100%', height: '100%'}} >{errorMessage}</div>;

        return data.data.name;
    }

    render() {
        return (
            <div style={{'backgroundColor': 'red', width: '100%', height: '100%'}}>
                {this.getContent()}
            </div>
        );
    }
}

Pane.propTypes = {
    isFetching: PropTypes.bool.isRequired,
    data: PropTypes.object
};

export default connect(
    state => ({
        data: getSelectedEntityData(state),
        isFetching: getSelectedEntityIsFetching(state)
    })
)(Pane);
