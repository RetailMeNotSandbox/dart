import React, { Component, PropTypes } from 'react';
import { connect } from 'react-redux';
import isEqual from 'lodash/isEqual';
import jp from 'jsplumb';
let jsPlumb = jp.jsPlumb;

import { fetchGraph, selectEntity, getGraph, getGraphIsFetching, getGraphErrorMessage } from 'api/';
import './index.css';


class Graph extends Component {

    // componentDidMount(){
    //     jsPlumb.ready(() => {
    //         const instance = jsPlumb.getInstance({
    //             container: 'graph-container',
    //             PaintStyle:{
    //                 strokeWidth:6,
    //                 stroke:"#567567",
    //                 outlineStroke:"black",
    //                 outlineWidth:1
    //             },
    //             Connector:[ "Bezier", { curviness: 30 } ],
    //             Endpoint:[ "Dot", { radius:5 } ],
    //             EndpointStyle : { fill: "#567567"  },
    //             Anchor : [ 0.5, 0.5, 1, 1 ]
    //         });
    //
    //         let endpointOptions = {
    //             anchor:'BottomCenter',
    //             maxConnections:1,
    //             endpoint:['Rectangle',{width:'1px', height:'1px' }],
    //             paintStyle:{fillStyle:'#00000', dashstyle:'3 3'},
    //             connectorStyle:{lineWidth:'1px',strokeStyle:'#000000'},
    //             connector:['Straight'],
    //         };
    //
    //         const a = instance.addEndpoint('node-a', endpointOptions);
    //         const b = instance.addEndpoint('node-b', endpointOptions);
    //
    //
    //         instance.connect({
    //             source: a,
    //             target: b
    //         });
    //
    //         // jsPlumb.draggable(a);
    //         // jsPlumb.draggable(b);
    //     });
    // }

    componentDidMount() {
        this.init();
    }

    componentDidUpdate(prevProps) {
        if (!isEqual(prevProps.entity, this.props.entity))
            this.init();
    }

    init() {
        const { fetchGraph, selectEntity, entity } = this.props;
        fetchGraph(entity);
        selectEntity(entity);
    }

    render() {
        const { isFetching, errorMessage, data } = this.props;

        if (isFetching)
            return <div style={{width: '100%', height: '100%'}} >Loading...</div>;
        if (errorMessage)
            return <div style={{width: '100%', height: '100%'}} >{errorMessage}</div>;

        return (
            <div id="graph-container" style={{width: '100%', height: '100%'}}>
                <div id="node-a" className="item" />
                <div id="node-b" className="item" />
                {data.nodes.map(node =>
                    <div key={node.entity_id}>{node.entity_id}</div>
                )}
            </div>
        );
    }
}

Graph.propTypes = {
    entity: PropTypes.shape({
        type: PropTypes.string.isRequired,
        id: PropTypes.string.isRequired
    }),
    isFetching: PropTypes.bool.isRequired,
    errorMessage: PropTypes.string,
    data: PropTypes.shape({
        edges: PropTypes.arrayOf(PropTypes.shape({
            destination_type: PropTypes.string.isRequired,
            destination_id: PropTypes.string.isRequired,
            source_type: PropTypes.string.isRequired,
            source_id: PropTypes.string.isRequired
        })),
        nodes: PropTypes.arrayOf(PropTypes.shape({
            entity_type: PropTypes.string.isRequired,
            entity_id: PropTypes.string.isRequired,
            name: PropTypes.string.isRequired,
            state: PropTypes.string.isRequired,
            sub_type: PropTypes.string
        }))
    }),
};

export default connect(
    (state, ownProps) => {
        return {
            isFetching: getGraphIsFetching(state, ownProps.entity),
            errorMessage: getGraphErrorMessage(state, ownProps.entity),
            data: getGraph(state, ownProps.entity),
        };
    },
    {
        fetchGraph,
        selectEntity
    }
)(Graph);
