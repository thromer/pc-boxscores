#!/bin/bash

set -o pipefail

shopt -s expand_aliases
source $HOME/.bash_script_aliases

PROJECT=pennantchase-256
LOCATION=us-west1
SERVICE=process-box-score
SA=eventarc-trigger@${PROJECT}.iam.gserviceaccount.com

ensure_eventarc_trigger_account $PROJECT $LOCATION $SERVICE $SA &&
    (gcloud --project=${PROJECT} eventarc triggers describe --location=$LOCATION boxscore >& /dev/null ||
	 gcloud --project=${PROJECT} eventarc triggers create \
		--location=${LOCATION} \
		--event-filters="type=google.cloud.storage.object.v1.finalized" \
		--event-filters="bucket=pc256-box-scores" \
		--destination-run-service=${SERVICE} \
		--service-account=$SA \
		boxscore)
