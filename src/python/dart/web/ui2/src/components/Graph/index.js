import React, { Component, PropTypes } from 'react';
import { connect } from 'react-redux';
import isEqual from 'lodash/isEqual';
import cytoscape from 'cytoscape';
import dagre from 'cytoscape-dagre';
cytoscape.use(dagre);

import { getGraph, getGraphIsFetching, getGraphErrorMessage, getSelectedEntity } from 'reducers/';
import { fetchGraph, selectEntity, fetchEntity } from 'actions/';
import './index.css';

let colorMap = state => {
    switch (state) {
        case 'QUEUED': return 'yellow';
        case 'PENDING': return 'yellow';
        case 'RUNNING': return 'orange';
        case 'FINISHING': return 'orange';
        case 'GENERATING': return 'orange';
        case 'COMPLETED': return 'green';
        case 'FAILED': return 'red';
        case 'SKIPPED': return 'black';
        case 'ACTIVE': return 'blue';
        case 'INACTIVE': return 'black';
        case 'DONE': return '#66512c';
        case 'HAS_NEVER_RUN': return 'grey';
        case 'TEMPLATE': return 'grey';
        default:
            return 'grey'
    }
};

let shapeMap = type => {
    switch (type) {
        case 'dataset': return 'rectangle';
        case 'action': return 'ellipse';
        case 'workflow': return 'diamond';
        case 'workflow_instance': return 'diamond';
        case 'trigger': return 'vee';
        case 'subscription': return 'hexagon';
        case 'datastore': return 'pentagon';
        case 'event': return 'star';
        default:
            return 'octagon'
    }
};

let parseGraph = ({ nodes, edges }) => ({
    nodes: nodes.map(n => ({ group: 'nodes', data: {
        entity_type: n.entity_type,
        entity_id: n.entity_id,
        name: n.name,
        state: n.state,
        sub_type: n.sub_type,
        color: colorMap(n.state),
        shape: shapeMap(n.entity_type),
        id: `${n.entity_type}-${n.entity_id}`,
        engine_name: n.engine_name,
        sub_graph_name: n.sub_graph_name
    }})),
    edges: edges.map(e => ({ group: 'edges', data: {
        source: `${e.source_type}-${e.source_id}`,
        target: `${e.destination_type}-${e.destination_id}`,
        id: `${e.source_type}-${e.source_id}-${e.destination_type}-${e.destination_id}`
    }})),
});


class Graph extends Component {

    componentDidMount() {
        this.init();

        this.cy = cytoscape({
            container: document.getElementById('graph-container'),
            style: cytoscape.stylesheet()
                .selector('node')
                .css({
                    'height': 100,
                    'width': 100,
                    'font-size': 10,
                    'label': 'data(name)',
                    'text-wrap': 'wrap',
                    'text-outline-color': 'data(color)',
                    'background-color': 'data(color)',
                    'color': 'black',
                    'shape': 'data(shape)'
                })
                .selector('edge')
                .css({
                    'width': 7,
                    'line-color': '#ffaaaa',
                    'target-arrow-shape': 'triangle',
                    'target-arrow-color': '#ffaaaa'
                })
                .selector(':selected')
                .css({
                    'border-color': 'purple',
                    'border-width': 10
                })
                .selector('.faded')
                .css({
                    'opacity': 0.20
                })
        });

        const { selectEntity, fetchEntity } = this.props;
        this.cy.on('select', 'node', evt => {
            let nodeData = evt.target.data();
            const entity = {
                type: nodeData.entity_type,
                id: nodeData.entity_id
            };

            fetchEntity(entity);
            selectEntity(entity);
        });
    }

    componentDidUpdate(prevProps) {
        if (!isEqual(prevProps.entity, this.props.entity))
            this.init();

        if (!isEqual(prevProps.data, this.props.data)) {
            this.cy.json({elements: parseGraph(this.props.data)});
            this.cy.layout({
                name: 'dagre',
                rankSep: 150,
                animate: true,
                animationDuration: 700,
                animationEasing: 'ease-out'
            }).run();
            this.cy.fit();
        }

        if (!isEqual(prevProps.selectedEntity, this.props.selectedEntity)) {
            if (prevProps.selectedEntity)
                this.select(prevProps.selectedEntity, false);
            if (this.props.selectedEntity)
                this.select(this.props.selectedEntity, true);
        }

    }

    select({ type, id }, select) {
        this.cy.$id(`${type}-${id}`)[select ? 'select' : 'unselect']();
    }

    init() {
        const { fetchGraph, selectEntity, entity } = this.props;
        fetchGraph(entity);
        selectEntity(entity);
    }

    render() {
        return <div
            id="graph-container"
            style={{
                width: '100%',
                backgroundColor: 'pink'
            }}
        />;
    }
}

        // const { isFetching, selectEntity, errorMessage, data } = this.props;
        //
        // if (isFetching)
        //     return <div style={{width: '100%', height: '100%'}} >Loading...</div>;
        // if (errorMessage)
        //     return <div style={{width: '100%', height: '100%'}} >{errorMessage}</div>;


                // {data.nodes.map(node =>
                //     <button
                //         key={node.entity_id}
                //         onClick={() => selectEntity({type: node.entity_type, id: node.entity_id})}
                //     >
                //         {node.entity_id}
                //     </button>
                // )}

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
    (state, props) => {
        return {
            isFetching: getGraphIsFetching(state, props.entity),
            errorMessage: getGraphErrorMessage(state, props.entity),
            data: getGraph(state, props.entity),
            selectedEntity: getSelectedEntity(state)
        };
    },
    {
        fetchGraph,
        selectEntity,
        fetchEntity
    }
)(Graph);
