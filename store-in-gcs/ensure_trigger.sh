#!/bin/bash

set -o pipefail

shopt -s expand_aliases
source $HOME/.bash_script_aliases

PROJECT=pennantchase-256
LOCATION=us-west1
TRIGGER_LOCATION=nam5
SERVICE=store-in-gcs
SA=eventarc-trigger@${PROJECT}.iam.gserviceaccount.com

ensure_eventarc_trigger_account $PROJECT $LOCATION $SERVICE $SA &&
    (gcloud --project=${PROJECT} eventarc triggers describe --location=$TRIGGER_LOCATION game-doc >& /dev/null ||
	 gcloud --project=${PROJECT} eventarc triggers create \
		--location=${TRIGGER_LOCATION} \
		--event-filters=type=google.cloud.firestore.document.v1.written \
		--event-filters=database='(default)' \
		--event-filters-path-pattern=document='mydb/{doc}' \
		--destination-run-service=store-in-gcs \
		--destination-run-region=${LOCATION} \
		--event-data-content-type=application/protobuf \
		--service-account=$SA \
		game-doc)
