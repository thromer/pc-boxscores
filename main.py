#!/usr/bin/env python3

# TODO someday
#  don't send if the message is already in the chatbox
#  don't send if the game was more than a couple days ago
# TODO also report the day

import re
import sys

from lib import analyze
from lib import pcweb
from google.cloud import exceptions, storage

# gcloud --project pennantchase-256 functions deploy --docker-registry=container_registry process_box_score --runtime python312 --trigger-resource pc256-box-scores  --trigger-event google.storage.object.finalize


def process_box_score(event, context):
    """Background Cloud Function to be triggered by Cloud Storage.

    Args:
        event (dict):  The dictionary with data specific to this type of event.
                       The `data` field contains a description of the event in
                       the Cloud Storage `object` format described here:
                       https://cloud.google.com/storage/docs/json_api/v1/objects#resource
        context (google.cloud.functions.Context): Metadata of triggering event.
    Returns:
        None; the output is written to Stackdriver Logging
    """

    # print('Event type: {}'.format(context.event_type))
    # print('Bucket: {}'.format(event['bucket']))
    # print('File: {}'.format(event['name']))
    # print('Metageneration: {}'.format(event['metageneration']))
    # print('Created: {}'.format(event['timeCreated']))
    # print('Updated: {}'.format(event['updated']))
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(event['bucket'])
    blob = bucket.get_blob(event['name'])
    print('Event ID: %s bucket: %s object: %s' % (context.event_id, bucket, blob))
    if event['name'].find('-replay') > 0:
        print('replay, skipping')
        return
    data = blob.download_as_text()
    messages = analyze.analyze(data)
    if messages:
        pc = pcweb.PcWeb('256')  # '1000' for testing
        # pc.send_to_thromer('stuff happened', '\n'.join(messages))
        for message in messages:
            pc.league_chat('%s [Day %s]' % (message, blob.metadata['day']), trailing_whitespace=int(blob.metadata['year']) % 5)
    
