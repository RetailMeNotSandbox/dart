import React, { Component } from 'react';
import { connect } from 'react-redux';

import { selectEntity, fetchEntity } from 'actions/';
import EntityInfo from './entity';

class DatastoreInfo extends Component {

    render = () => <EntityInfo
        entity={this.props.entity}
        data={this.props.data}
    />;
}

export default connect(
    (state,) => ({

    }), {
        selectEntity,
        fetchEntity
    }
)(DatastoreInfo);
