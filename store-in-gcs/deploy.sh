#!/bin/bash 
cd $(realpath "$(dirname "${BASH_SOURCE[0]}")") &&
    gcloud --project pennantchase-256 functions deploy pubsub_to_gcs \
	   --gen2 --region us-central1 --runtime python312 \
	   --trigger-location nam5 \
	   --trigger-event-filters=database='(default)' \
	   --trigger-event-filters document='mydb/{username}' \
	   --trigger-event-filters type=google.cloud.firestore.document.v1.written
