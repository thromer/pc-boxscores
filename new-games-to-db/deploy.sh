#!/bin/bash 
cd $(realpath "$(dirname "${BASH_SOURCE[0]}")") &&
    gcloud --project pennantchase-256 \
	   functions deploy --gen2 --region=us-central1 --runtime=python312 \
	   new_games_to_db --trigger-http
