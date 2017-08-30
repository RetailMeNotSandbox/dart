import React, { Component, PropTypes } from 'react';
import { connect } from 'react-redux';
import Tabs from 'react-toolbox/lib/tabs/Tabs';
import Tab from 'react-toolbox/lib/tabs/Tab';
import { SchemaForm } from 'react-schema-form';
import axios from 'axios';
import { Scrollbars } from 'react-custom-scrollbars';

import { getTabs, getSelectedTabIndex } from 'reducers/';
import { addTab, selectTab, fetchEntity } from 'actions/'
import EntityInfo from 'components/EntityInfo';

class Pane extends Component {

    render() {
        return (
            <Tabs index={this.props.selected} >
                {this.props.tabs.map((t, i) => <Tab
                    label={t.name}
                    key={t.id}
                    onClick={() => this.props.selectTab(i)}
                >
                    <EntityInfo entity={t.entity} />
                </Tab>)}
                <Tab label='+' onClick={this.props.addTab} />
            </Tabs>
        );
    }
}




Pane.propTypes = {
};

export default connect(
    state => ({
        tabs: getTabs(state),
        selected: getSelectedTabIndex(state)
    }),
    {
        selectTab,
        addTab,
        fetchEntity
    }
)(Pane);
