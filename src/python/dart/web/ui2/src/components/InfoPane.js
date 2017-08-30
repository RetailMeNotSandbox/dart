import React from 'react';
import SplitterLayout from 'react-panelgroup';
import EntityTabs from 'components/EntityTabs';
import EntityToggler from 'components/EntityToggler';

const InfoPane = (props) => {
    const entity = props.entity;
    return (
        <SplitterLayout
            direction="column"
            borderColor="black"
        >
            <EntityTabs />
            <EntityToggler entity={entity} />
        </SplitterLayout>
    );
};

export default InfoPane;
