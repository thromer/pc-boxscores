#!/bin/bash 
cd $(realpath "$(dirname "${BASH_SOURCE[0]}")") &&
    gcloud --project pennantchase-256 \
	   functions deploy --gen2 --region=us-central1 --runtime=python312 \
	   process_box_score \
	   --trigger-location=us-west1 --trigger-resource=pc256-box-scores \
	   --trigger-event=google.storage.object.finalize
