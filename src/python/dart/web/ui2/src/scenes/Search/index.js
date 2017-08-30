import React, { Component } from 'react';
import { connect } from 'react-redux';
import AutoComplete from 'material-ui/AutoComplete';
import { push } from 'react-router-redux';

import { search } from 'actions/';
import { getSearchResults, getSearchIsFetching } from 'reducers/';
import WorkflowSearch from 'components/WorkflowSearch';

class SearchScene extends Component {

    render() {
        return <WorkflowSearch
            onSelect={ id => this.props.push(`/graph/workflow/${id}`) }
            style={{marginLeft: 50, marginRight: 50}}
        />;
    }
}

export default connect(
    state => ({
    }),
    {
        push
    }
)(SearchScene);
