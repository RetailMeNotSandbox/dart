#!/bin/sh

DOCKER_IMAGE=${2}

source ./docker-local-init.sh
pushd ../../ > /dev/null


$(aws ecr get-login)
docker push ${DOCKER_IMAGE}


popd > /dev/null
