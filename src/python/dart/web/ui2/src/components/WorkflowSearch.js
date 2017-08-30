import React, { Component } from 'react';
import { connect } from 'react-redux';
import AutoComplete from 'material-ui/AutoComplete';

import { search } from 'actions/';
import { getSearchResults, getSearchIsFetching } from 'reducers/';

class WorkflowSearch extends Component {

    getSearchOptions() {
        const { isFetching, searchOptions } = this.props;
        if (isFetching || !searchOptions)
            return [];

        return searchOptions;
    }

    select(value, index) {
        if (index === -1 && this.getSearchOptions().length > 0)
            index = 0;

        if (index === -1)
            return;

        this.props.onSelect(this.getSearchOptions()[index].id);
    }

    render() {
        const dataSource = this.getSearchOptions().map(w => `${w.id} - ${w.data.name}`);
        const onUpdate = v => this.props.search(v);
        return <AutoComplete
            hintText="Type anything"
            dataSource={dataSource}
            onUpdateInput={onUpdate}
            floatingLabelText="Full width"
            fullWidth={true}
            onNewRequest={this.select.bind(this)}
        />;
    }
}

export default connect(
    state => ({
        isFetching: getSearchIsFetching(state),
        searchOptions: getSearchResults(state)
    }),
    {
        search
    }
)(WorkflowSearch);
