#!/usr/bin/env bash
set -euo pipefail

SENTINELPAY_REGION="${SENTINELPAY_REGION:-ap-southeast-2}"
SENTINELPAY_MODEL_IMAGE_TAG="${SENTINELPAY_MODEL_IMAGE_TAG:-v4}"
export AWS_SDK_UA_APP_ID=AWSSkill-SageMaker
SENTINELPAY_REPOSITORY="sentinelpay-model-training-dev"
SENTINELPAY_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text --region "$SENTINELPAY_REGION")"
SENTINELPAY_REGISTRY="${SENTINELPAY_ACCOUNT_ID}.dkr.ecr.${SENTINELPAY_REGION}.amazonaws.com"
SENTINELPAY_IMAGE_URI="${SENTINELPAY_REGISTRY}/${SENTINELPAY_REPOSITORY}:${SENTINELPAY_MODEL_IMAGE_TAG}"

aws ecr get-login-password --region "$SENTINELPAY_REGION" \
  | docker login --username AWS --password-stdin "$SENTINELPAY_REGISTRY"

docker buildx build --platform linux/amd64 --provenance=false --push \
  --file src/lambda/model_training/Dockerfile \
  --tag "$SENTINELPAY_IMAGE_URI" .

printf 'Pushed model-training Lambda image: %s\n' "$SENTINELPAY_IMAGE_URI"
