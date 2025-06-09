#!/bin/bash

# WIP! See https://claude.ai/chat/f9d1601a-c975-48a7-97a2-8a1d98c96cdf
# Check whether we set up any Pubsub topics already (other than those magically created by GCF).

set -o pipefail

shopt -s expand_aliases
source $HOME/.bash_script_aliases

PROJECT=pennantchase-256
LOCATION=us-west1
TRIGGER_LOCATION=us-central1  # Supposed to work for nam5, location of '(default)'
SERVICE=process-box-score
SA=eventarc-trigger@${PROJECT}.iam.gserviceaccount.com

ensure_eventarc_trigger_account $PROJECT ${SERVICE} $SA &&
    (gcloud --project=${PROJECT} eventarc triggers describe --location=$LOCATION game-doc >& /dev/null ||
	 gcloud --project=${PROJECT} eventarc triggers create \
		--location=${TRIGGER_LOCATION} \
		--event-filters=type=google.cloud.firestore.document.v1.written \
		--event-filters=database='(default)' \
		--event-filters-path-pattern=document='mydb/{doc}' \
		--destination-run-service=store-in-gcs \
		--event-data-content-type=application/protobuf \
		--service-account=$SA \
		game-doc)
