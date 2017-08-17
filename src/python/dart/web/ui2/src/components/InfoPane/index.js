import React from 'react';
import SplitterLayout from 'react-panelgroup';
import Top from './Top';
import Middle from './Middle';
import Bottom from './Bottom';

const InfoPane = () => {
    return (
        <SplitterLayout direction="column" style={{width: '100%', height: '100%'}}>
            <Top />
            <Middle />
            <Bottom />
        </SplitterLayout>
    );
};

export default InfoPane;
