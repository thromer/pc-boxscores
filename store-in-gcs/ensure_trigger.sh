#!/bin/bash

set -o pipefail

shopt -s expand_aliases
source $HOME/.bash_script_aliases

PROJECT=pennantchase-256
LOCATION=us-west1
SERVICE=store-in-gcs
SA=eventarc-trigger@${PROJECT}.iam.gserviceaccount.com

# TODO refactor to remove reference to process-box-score

ensure_eventarc_trigger_account $PROJECT ${SERVICE},process-box-score $SA &&
    (gcloud --project=${PROJECT} eventarc triggers describe --location=$LOCATION game-doc >& /dev/null ||
	 gcloud --project=${PROJECT} eventarc triggers create \
		--location=${LOCATION} \
		--event-filters=type=google.cloud.firestore.document.v1.written \
		--event-filters=database='db-us-west1' \
		--event-filters-path-pattern=document='mydb/{doc}' \
		--destination-run-service=store-in-gcs \
		--event-data-content-type=application/protobuf \
		--service-account=$SA \
		game-doc)
