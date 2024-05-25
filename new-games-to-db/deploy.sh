#!/bin/bash 
cd $(realpath "$(dirname "${BASH_SOURCE[0]}")") &&
    gcloud --project pennantchase-256 \
	   functions deploy --gen2 --region us-central1 \
	   new_games_to_db --runtime python312 --trigger-http
