#!/bin/bash 
cd $(realpath "$(dirname "${BASH_SOURCE[0]}")") &&
    gcloud --project pennantchase-256 \
	   functions deploy --gen2 --region=us-west1 --runtime=python312 \
	   pubsub_to_gcs \
	   --trigger-location=nam5 \
	   --trigger-event-filters=database='(default)' \
	   --trigger-event-filters-path-pattern=document='mydb/{username}' \
	   --trigger-event-filters=type=google.cloud.firestore.document.v1.written

# https://cloud.google.com/functions/docs/calling/cloud-firestore#deploy_the_hello_function
