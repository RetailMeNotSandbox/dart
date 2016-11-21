#
# Usage:
# - python src/python/dart/tool/export_swagger_definitions.py src/python/dart/web/api/swagger.yaml
#
from __future__ import print_function

import filecmp
import os
import sys
from yaml import dump
try:
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Dumper

from dart.model.query import Operator, Direction
from dart.schema.action import action_schema
from dart.schema.dataset import columns_schema, dataset_schema
from dart.schema.datastore import datastore_schema
from dart.schema.engine import engine_schema, subgraph_definition_schema
from dart.schema.event import event_schema
from dart.schema.subscription import subscription_schema
from dart.schema.trigger import trigger_schema, trigger_type_schema
from dart.schema.workflow import workflow_schema, workflow_instance_schema


def main():
    """
    This will read in the swagger.yaml file and replace everything in the
    file after "definitions:" with the content of export_swagger_definitions.

    If the --dry-run flag is specified, then the tool will produce an updated
    swagger specification and check it against the original. If it differs,
    the tool will exit with an error code and prompt the user to re-run the
    tool without the flag and commit the resulting changes. This is intended
    to be a safety check to use in the build to remind developers to update
    the swagger when they update the schemas.
    """
    dry_run = False
    args = list(sys.argv[1:])
    if '--dry-run' in args:
        args.remove('--dry-run')
        dry_run = True

    if not args:
        print("Usage: [--dry-run] <path-to-swagger-spec>", file=sys.stderr)
        return 1

    swagger_spec_path = args[0]
    updated_swagger_spec_path = swagger_spec_path + '.tmp'

    with open(swagger_spec_path, 'rt') as input_file:
        with open(updated_swagger_spec_path, 'wt') as output_file:
            for line in input_file:
                if line.strip().startswith('definitions:'):
                    break
                output_file.write(line)
            export_swagger_definitions(output_file)

    if dry_run:
        if filecmp.cmp(swagger_spec_path, updated_swagger_spec_path):
            print("No changes.")
            os.remove(updated_swagger_spec_path)
            return 0
        else:
            print("The generated swagger specification differs from %s" % swagger_spec_path, file=sys.stderr)
            print("Please re-run this tool without --dry-run and commit the resulting changes.", file=sys.stderr)
            return 1

    os.rename(updated_swagger_spec_path, swagger_spec_path)
    print("Updated %s" % swagger_spec_path)
    return 0


def export_swagger_definitions(out):
    data = {
        'definitions': {
            'Action': action_schema({'type': 'object', 'x-nullable': True}),
            'ActionResponse': object_response_schema('Action'),
            'ActionsResponse': array_response_schema('Action'),
            'PagedActionsResponse': paged_response_schema('Action'),

            'ActionContext': action_context_schema(),
            'ActionContextResponse': object_response_schema('ActionContext'),

            'ActionResult': action_result_schema(),

            'Dataset': dataset_schema(),
            'DatasetResponse': object_response_schema('Dataset'),
            'PagedDatasetsResponse': paged_response_schema('Dataset'),

            'Datastore': datastore_schema({'type': 'object', 'x-nullable': True}),
            'DatastoreResponse': object_response_schema('Datastore'),
            'PagedDatastoresResponse': paged_response_schema('Datastore'),

            'Engine': engine_schema(),
            'EngineResponse': object_response_schema('Engine'),
            'PagedEnginesResponse': paged_response_schema('Engine'),

            'ErrorResponse': error_response_schema(),

            'Event': event_schema(),
            'EventResponse': object_response_schema('Event'),
            'PagedEventsResponse': paged_response_schema('Event'),

            'Filter': filter_schema(),

            'GraphEntityIdentifier': graph_entity_identifier_schema(),
            'GraphEntityIdentifierResponse': object_response_schema('GraphEntityIdentifier'),
            'GraphEntityIdentifiersResponse': array_response_schema('GraphEntityIdentifier'),

            'GraphEntity': graph_entity_schema(),
            'GraphEntityResponse': object_response_schema('GraphEntity'),

            'JSONPatch': json_patch_schema(),

            'JSONSchema': json_schema_schema(),
            'JSONSchemaResponse': object_response_schema('JSONSchema'),

            'ObjectResponse': object_response_schema('object'),
            'ObjectsResponse': array_response_schema('object'),
            'PagedObjectsResponse': paged_response_schema('object'),

            'OKResponse': ok_response_schema(),

            'OrderBy': order_by_schema(),

            'Subgraph': sub_graph_schema(),
            'SubgraphResponse': object_response_schema('Subgraph'),

            'SubgraphDefinition': {'type': 'object'}, #subgraph_definition_schema([{'type': 'object'}], [{'type': 'object'}], {'type': 'object'}),
            'SubgraphDefinitionResponse': object_response_schema('SubgraphDefinition'),

            'Subscription': subscription_schema(),
            'SubscriptionResponse': object_response_schema('Subscription'),
            'PagedSubscriptionsResponse': paged_response_schema('Subscription'),

            'SubscriptionElement': subscription_element_schema(),
            'PagedSubscriptionElementsResponse': paged_response_schema('SubscriptionElement'),

            'Trigger': trigger_schema({'type': 'object'}),
            'TriggerResponse': object_response_schema('Trigger'),
            'PagedTriggersResponse': paged_response_schema('Trigger'),

            'TriggerType': trigger_type_schema(),
            'PagedTriggerTypesResponse': paged_response_schema('TriggerType'),

            'Workflow': workflow_schema(),
            'WorkflowResponse': object_response_schema('Workflow'),
            'PagedWorkflowsResponse': paged_response_schema('Workflow'),

            'WorkflowInstance': workflow_instance_schema(),
            'WorkflowInstanceResponse': object_response_schema('WorkflowInstance'),
            'PagedWorkflowInstancesResponse': paged_response_schema('WorkflowInstance')
        }
    }
    fix_up(data, data, [None])
    dump(data, out, Dumper=Dumper, default_style=None, default_flow_style=False, explicit_start=False, explicit_end=False)


def action_context_schema():
    return {'type': 'object'}


def action_result_schema():
    return {'type': 'object'}


def error_response_schema():
    return {
        'type': 'object',
        'properties': {
            'results': {
                'type': 'string',
                'enum': ["ERROR"]
            },
            'error_message': {
                'type': 'string'
            }
        }
    }


def filter_schema():
    return {
        'type': 'object',
        'properties': {
            'key': {
                'type': 'string'
            },
            'operator': {
                'type': 'string',
                'enum': [getattr(Operator, attr) for attr in dir(Operator) if not attr.startswith('__')]
            },
            'value': {
                'type': 'string'
            }
        }
    }


def graph_entity_identifier_schema():
    return {
        'type': 'object',
        'properties': {
            'entity_type': {
                'type': 'string'
            },
            'entity_id': {
                'type': 'string'
            },
            'name': {
                'type': 'string'
            },
        }
    }


def graph_entity_schema():
    return {
        'type': 'object',
        'properties': {
            'entity_type': {
                'type': 'string'
            },
            'entity_id': {
                'type': 'string'
            },
            'name': {
                'type': 'string'
            },
            'state': {
                'type': 'string'
            },
            'sub_type': {
                'type': 'string'
            },
            'related_type': {
                'type': 'string'
            },
            'related_id': {
                'type': 'string'
            },
            'related_is_a': {
                'type': 'string'
            },
        }
    }


def json_patch_schema():
    return {
        'type': 'object',
        'description': "JSON Patch object as defined by http://json.schemastore.org/json-patch"
    }


def json_schema_schema():
    return {
        'type': 'object',
        'description': "JSON Schema object as defined by http://json-schema.org/schema"
    }


def ok_response_schema():
    return {
        'type': 'object',
        'properties': {
            'results': {
                'type': 'string',
                'enum': ["OK"]
            }
        }
    }


def order_by_schema():
    return {
        'type': 'object',
        'properties': {
            'key': {
                'type': 'string'
            },
            'direction': {
                'type': 'string',
                'enum': [getattr(Direction, attr) for attr in dir(Direction) if not attr.startswith('__')]
            }
        }
    }


def subscription_element_schema():
    return {'type': 'object'}


def sub_graph_schema():
    return {'type': 'object'}


def object_response_schema(type_name):
    if type_name == 'object':
        type_info = {
            'type': 'object'
        }
    else:
        type_info = {
            '$ref': '#/definitions/%s' % type_name
        }
    return {
        'type': 'object',
        'properties': {
            'results': type_info
        }
    }


def array_response_schema(type_name):
    if type_name == 'object':
        type_info = {
            'type': 'object'
        }
    else:
        type_info = {
            '$ref': '#/definitions/%s' % type_name
        }
    return {
        'type': 'object',
        'properties': {
            'results': {
                'type': 'array',
                'items': type_info
            }
        }
    }


def paged_response_schema(type_name):
    if type_name == 'object':
        type_info = {
            'type': 'object'
        }
    else:
        type_info = {
            '$ref': '#/definitions/%s' % type_name
        }
    return {
        'type': 'object',
        'properties': {
            'results': {
                'type': 'array',
                'items': type_info
            },
            'limit': {
                'type': 'integer'
            },
            'offset': {
                'type': 'integer'
            },
            'total': {
                'type': 'integer'
            }
        }
    }


def fix_up(data, root, path):
    """
    Fix up the JSON schemas from the dart.schema package and transform them into
    Swagger compatible definitions. Transform any embedded object definitions into
    top level definitions. Remove the use of readonly and placeholder attributes.
    Remove the use of null defaults as they aren't yet fully supported by the
    Open API Specification.

    See https://github.com/OAI/OpenAPI-Specification/issues/229

    :param data: The current dictionary in the traversal
    :param root: The root dictionary
    :param path: A list containing the path to root
    :return:
    """
    parent = path[-1]
    for key, value in data.items():
        if key == 'type':
            if isinstance(value, list):
                try:
                    value.remove('null')
                except ValueError:
                    pass
                data[key] = value[0]
                data['x-nullable'] = True
        elif key == 'readonly':
            del data[key]
        elif key == 'placeholder':
            del data[key]
        elif key == 'default' and value is None:
            del data[key]
        # The following code was added to work around some changes introduced in swagger-codegen v2.2.0
        # that requires regular expressions to be stated using Perl style /pattern/modifier conventions.
        # Unfortunately this breaks JSON Schema validation of the same properties.
        #elif key == 'pattern' and not value.startswith('/'):
        #    data[key] = '/%s/' % value
        elif key in ['columns', 'partitions', 'supported_action_types'] and parent == 'properties':
            if key in ['columns', 'partitions']:
                schema = 'Column'
            elif key == 'supported_action_types':
                schema = 'ActionType'
            items = value['items']
            value['items'] = {
                '$ref': ('#/definitions/%s' % schema)
            }
            if schema not in root['definitions']:
                root['definitions'][schema] = items
                fix_up(items, root, ['definitions', schema])
            path.append(key)
            fix_up(value, root, path)
            path.pop()
        elif key in ['data', 'data_format'] and parent == 'properties':
            if key == 'data':
                schema = '%sData' % path[2]
            elif key == 'data_format':
                schema = 'DataFormat'
            data[key] = {
                '$ref': ('#/definitions/%s' % schema)
            }
            root['definitions'][schema] = value
            fix_up(value, root, ['definitions', schema])
        elif isinstance(value, dict):
            path.append(key)
            fix_up(value, root, path)
            path.pop()


if __name__ == '__main__':
    sys.exit(main())
