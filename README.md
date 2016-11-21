#dart
![alt tag](http://i.imgur.com/lJqoDhB.png "dart")

## table of contents
* [what is dart](#what-is-dart)
* [prerequisites](#prerequisites)
* [bootstrapping](#bootstrapping)
* [local development setup](#local-development-setup)
* [usage](#usage)
* [dart development](#dart-development)
* [engine development](#engine-development)
* [REST api documentation](#rest-api-documentation)

## what is dart
Dart, short for "data mart à la carte", is a self-service data workflow solution that facilitates the creation,
transformation, and movement of data using data engines, primarily in the context of AWS.  Put another way, it is
a system to facilitate moving data in and out of datastores like S3, RDS, Redshift, EMR, DynamoDB, something custom,
etc.

The dart UI is built on top of the dart REST api, is data-driven, and is a combination of
[AngularJS](https://angularjs.org/), [Angular Material](https://material.angularjs.org), and
[Angular Schema Form](http://schemaform.io/).  The UI assists with self-service, while the REST api allows dart to be
plugged into engineering systems.

Below is a list of dart entities to become familiar with.

###### engine
An engine advertizes its supported actions using JSON schema, and interacts with dart over the REST api for
* engine registration
* action check-out
* action check-in
* and more...

Engines are able to understand and interact with datasets.

###### dataset
A dataset is a platform agnostic definition of data living in S3, which includes:
* the S3 root location
* the fields and types (or JSON paths for lines of JSON data)
* the load type (e.g. are new files merged, inserted, reloaded, etc.?)
* compression type
* etc.

###### datastore
A datastore is intended to capture attributes of a particular datastore technology instance (e.g. a Redshift cluster,
an EMR cluster, etc.) including its host, port, connection url, etc.  Engine's can describe input options for their
datastore types via JSON schema.

###### action
An action entity is an instance of an action type specified by an engine.  These contain user supplied arguments that
adhere to the engine's JSON schema for that action type.  In addition, the action contains state information, timing
information, and optional alert email addresses.

###### workflow
A workflow is a collection of actions in the __TEMPLATE__ state to be run on the specified datastore. When a workflow
runs, its template actions are copied to a workflow instance and run.  If the specified datastore for the workflow is
in the __TEMPLATE__ state, then a new datastore will be created based on it for the workflow instance.

###### workflow instance
An instance of a running workflow with state and timing information.

###### subscription
A subscription is a stateful listing of dataset files on S3.  Unprocessed subscription elements are considered
"unconsumed".  When an engine provides an action with an action type name of "consume_subscription", dart will assign
unconsumed subscription elements to that action at run time.  Engines can request these subscription elements
through a REST api call.

###### trigger
A trigger initiates a workflow.  There are several types of triggers available:
* scheduled - triggers a workflow based on a CRON schedule
* workflow_completion - triggering upon successful workflow completion
* subscription_batch - creates subscription element batches based on a file size threshold, and triggers workflows as
they are ready
* super - takes other triggers as inputs and fires when __ALL__ have fired or __ANY__ have fired
* event - triggers a workflow based on an "event" entity (essentially an SQS message sent from a source outside of dart)

Additionally, workflows can be triggered manually via the REST api or the UI.

###### event
An event is just a named identifier so that SQS messages in the dart trigger call format can be crafted outside of
dart (with a particular event id) in order to trigger dart workflows.

## prerequisites

* obtain an AWS account
  * configure the AWS CLI locally
  * create a VPC
  * create an EC2 key-pair for dart
  * create a Route53 hosted zone
* install python
* install pip
* install libxmlsec1
* install libmagic
* install git
* install npm
* install grunt
* install bower
* install docker
* install docker-machine
* run the bash snippets below

###### install python libraries
*feel free to create and use an isolated python virtualenv*
```
pip install -r src/python/requirements.txt
pip install -e src/python/.
```

###### docker setup
```
cd tools/docker
./docker-local-setup.sh
```

###### install bower components
```
cd src/python/dart/web/ui
bower install
```

## bootstrapping

Following the instructions below will result in all necessary docker images built and pushed to ECR, an isolated
dart environment, as well as a generated config file saved in S3. Dart is primarily driven by a single YAML config
file, in combination with a few environment variables.

##### step 1
Copy and rename `dart-config-template-EXAMPLE.yaml` outside of the dart project, and modify it to suit
your needs.  For the remainder of this example, let's assume this file lives in a sibling directory next
to the dart project: `../my-dart-config-project/dart-config-template.yaml`

tips:
* Fields marked as `...TBD...` will be populated during deployment
* Fields with `my` or `mycompany` should be changed (for urls, your key-pair name, etc.)
* If your VPC requires VPN access, change one or both of the `OpenCidrIp1` and `OpenCidrIp2` values
  accordingly.
* Most other fields should be self-explanatory, and comments have been added otherwise

##### step 2
Run the following bash snippets to create a "stage" environment:
*(`AWS_SECRET_ACCESS_KEY` and `AWS_ACCESS_KEY_ID` are assumed to be in the current shell environment)*

```
export PYTHONPATH=/full-path-to-your-dart-project-root/src/python:${PYTHONPATH}
```
```
read -s -p "Your email server password (used by dart to send alerts):" DART_EMAIL_PASSWORD
read -s -p "Your chosen RDS password:" DART_RDS_PASSWORD
export DART_EMAIL_PASSWORD
export DART_RDS_PASSWORD
```
```
python src/python/dart/deploy/full_environment_create.py \
  -n stage \
  -i ../my-dart-config-project/dart-config-template.yaml \
  -o s3://mycompany-dart-stage-config/dart-stage.yaml \
  -u my_dart_alert_email_address@mycompany.com
```

When the command above executes, it will use a combination of AWS CloudFormation and boto to provision a new dart
environment, and write the generated config file to the specified location,
`s3://mycompany-dart-stage-config/dart-stage.yaml`. See the source of `full_environment_create.py` for more
insight.

## local development setup

Dart is primarily driven by a single YAML config file, in combination with a few environment variables.  For local
development, we will use a config file similar to the one in the [bootstrapping](#bootstrapping) step, with a few
differences:

* Instead of RDS, it is preferable to use a dockerized postgres instance
* Instead of SQS, it is preferable to use a dockerized elasticmq instance
* Instead of running engine tasks in ECS, it is preferable to have the engine worker fork them locally

Make sure your config file has the "local_setup" section set properly, since this will be used next.  Additionally,
it is assumed you have already built the elasticmq docker image and updated your local dart config __either__ buy
running the [bootstrapping](#bootstrapping) step, __or__ by manually running this snippet and updating your local
dart config (`local_setup.elasticmq_docker_image`) with the matching value from the snippet below:

```
cd tools/docker
docker build -f tools/docker/Dockerfile-elasticmq -t <my-elasticmq-docker-image-name> .

```

##### starting

Run the postgres instance:
```
cd tools/docker
export DART_CONFIG=../my-dart-config-project/dart-config-local.yaml
./docker-local-run-postgres.sh
```
Run the elasticmq instance:
```
cd tools/docker
export DART_CONFIG=../my-dart-config-project/dart-config-local.yaml
./docker-local-run-elasticmq.sh
```

Run the dart components:
*(`AWS_SECRET_ACCESS_KEY` and `AWS_ACCESS_KEY_ID` are assumed to be in the current shell environment)*


###### flask web application
```
cd src/python/dart/web
export PYTHONPATH=/full-path-to-your-dart-project-root/src/python:${PYTHONPATH}
export DART_ROLE=web
export DART_CONFIG=../my-dart-config-project/dart-config-local.yaml
python server.py
```

###### trigger worker
```
cd src/python/dart/worker
export PYTHONPATH=/full-path-to-your-dart-project-root/src/python:${PYTHONPATH}
export DART_ROLE=web
export DART_CONFIG=../my-dart-config-project/dart-config-local.yaml
python trigger.py
```

###### engine worker
```
cd src/python/dart/worker
export PYTHONPATH=/full-path-to-your-dart-project-root/src/python:${PYTHONPATH}
export DART_ROLE=worker
export DART_CONFIG=../my-dart-config-project/dart-config-local.yaml
python engine.py
```

###### subscription worker
```
cd src/python/dart/worker
export PYTHONPATH=/full-path-to-your-dart-project-root/src/python:${PYTHONPATH}
export DART_ROLE=web
export DART_CONFIG=../my-dart-config-project/dart-config-local.yaml
python subscription.py
```

## usage

If running locally with the default flask configuration, navigate to http://localhost:5000.  If you have deployed
to AWS, navigate to http://your-dart-host-and-port.

For a demonstration of dart's capabilities, follow these steps:

1. navigate to the "datastores" link in the __entities__ section of the navbar (not the managers section)
1. create a new "no_op_engine" datastore with default values by clicking on the "+" button and then clicking "save"
1. refresh the page
1. click on the "more options" vertical elipses on the left side of the row
1. click on "graph", wait for the graph to load
1. click on "add > no_op_engine > workflow chaining demo"
1. click on "file > save"
1. click on the top most workflow (blue, diamond shaped) icon
1. click on "edit > run"

In short, familiarity with [dart entities](#what-is-dart) allows a variety of workflow chains to be created.

For example, an EMR workflow can be created to parse web logs and store them in a delimited format on S3, which is
referred to by an existing dataset.  Completion of this workflow triggers a Redshift workflow to load the data,
perform aggregations, and upload to another dataset location.  This workflow completion triggers an S3
workflow to load that copies the data to the front-end web team's AWS bucket.  Completion of this workflow triggers
a DynamoDB workflow to load the aggregated data into a DynamoDB table, supporting a front-end feature.

## dart development

Dart uses postgres 9.4+ for its JSONB columns.  This allows dart models to be fluid but consistent.  That is, most
dart models have the fields: `id`, `version_id`, `created`, `updated`, and `data` (the JSONB column).  Dart has
custom deserialization that relies on parsing the python docstring for types (recursively).  This way, the data can
be stored in plan JSON format, rather than relying on modifiers as in jsonpickle.  So keep the docstrings up
to date and accurate!

Be sure to keep the black-box integration tests up to date and passing.

## engine development

Engines are completely decoupled from dart by design.  The dart engine source code lives in the same repository out
of convenience, but this is by no means a requirement.  Engines can be added to dart source itself for general use
cases, but they can also be developed outside of dart for custom use cases, so long as they adhere to these
conventions:

* engines must make a registration REST api call that informs dart about the ECS task definitions
* engines are instantiated as ECS tasks to process one action at a time
* dart will override the ECS task definition at run time to supply one environment variable that informs the running
engine which action is being run: `DART_ACTION_ID`
* a REST api call must be made to check-out this action
* a REST api call must be made to check-in this action upon completion
* if writing a `consume_subscription` action, a REST api call should be made to retrieve the assigned subscription
elements

## REST api documentation

See the draft API specification in Swagger 2.0 format at `src/python/dart/web/api/swagger.yaml` or via Swagger-UI
at http://your-dart-host-and-port/apidocs/index.html
 
See the source code at `src/python/dart/web/api` for implementation details.
