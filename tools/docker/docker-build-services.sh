#!/bin/sh -e

[[ -z "${DART_CONFIG}" ]] && echo "environment variable needs to be set: DART_CONFIG" && exit 1
source ../util.sh
source ./docker-local-init.sh

pushd ../../ > /dev/null


echo "reading configuration: ${DART_CONFIG}"
OLD_IFS=${IFS}
IFS=
CONFIG="$(DART_ROLE=tool dart_conf)"
DOCKER_IMAGE_FLASK=$(dart_conf_value "${CONFIG}" "$.cloudformation_stacks.web.boto_args.Parameters[@.ParameterKey is 'FlaskWorkerDockerImage'][0].ParameterValue")
DOCKER_IMAGE_WORKER_TRIGGER=$(dart_conf_value "${CONFIG}" "$.cloudformation_stacks.'trigger-worker'.boto_args.Parameters[@.ParameterKey is 'TriggerWorkerDockerImage'][0].ParameterValue")
IFS=${OLD_IFS}

set -x
docker build -f tools/docker/Dockerfile-flask               -t ${DOCKER_IMAGE_FLASK} .
docker build -f tools/docker/Dockerfile-trigger-worker      -t ${DOCKER_IMAGE_WORKER_TRIGGER} .
set +x

REMOVABLE=$(docker images -f "dangling=true" -q)
[[ -n "${REMOVABLE}" ]] && docker rmi ${REMOVABLE}


popd > /dev/null
