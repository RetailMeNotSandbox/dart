#!/bin/sh -e

[[ -z "${DART_CONFIG}" ]] && echo "environment variable needs to be set: DART_CONFIG" && exit 1
source ../util.sh
source ./docker-local-init.sh

pushd ../../ > /dev/null

ECR_ID=${ECR_ID:-249030517958} # by default use eng account ecr id -249030517958. Can provide ECR_ID=XXX in commandline to override

echo "reading configuration: ${DART_CONFIG}"
OLD_IFS=${IFS}
IFS=
CONFIG="$(DART_ROLE=tool dart_conf)"
DOCKER_IMAGE_FLASK=$(dart_conf_value "${CONFIG}" "$.cloudformation_stacks.web.boto_args.Parameters[@.ParameterKey is 'FlaskWorkerDockerImage'][0].ParameterValue")
DOCKER_IMAGE_WORKER_TRIGGER=$(dart_conf_value "${CONFIG}" "$.cloudformation_stacks.'trigger-worker'.boto_args.Parameters[@.ParameterKey is 'TriggerWorkerDockerImage'][0].ParameterValue")
IFS=${OLD_IFS}

$(aws ecr get-login --registry-ids $ECR_ID)
set -x
docker push ${DOCKER_IMAGE_FLASK}
docker push ${DOCKER_IMAGE_WORKER_TRIGGER}
set +x


popd > /dev/null
