#!/usr/bin/env python3

# TODO someday
#  don't send if the message is already in the chatbox
#  don't send if the game was more than a couple days ago
# TODO also report the day
# TODO would be nice to move to a subdirectory

import flask
from typing import Any, cast

from lib import analyze
from lib import pcweb
from cloudevents.http import CloudEvent, from_http
from google.cloud import storage

app = flask.Flask(__name__)

def process_box_score(event: CloudEvent):
    storage_client = storage.Client()
    bucket_name = event.data['bucket']
    bucket = storage_client.get_bucket(bucket_name)
    blob_name = event.data['name']
    blob = bucket.get_blob(blob_name)
    if blob is None:
        raise Exception(f"Object not found gs://{bucket_name}/{blob_name}")
    print(f'bucket: {bucket} object: {blob}')
    if blob_name.find('-replay') > 0:
        print('replay, skipping')
        return
    data = blob.download_as_text()
    messages = analyze.analyze(data)
    if messages:
        pc = pcweb.PcWeb('256')  # '1000' for testing
        # pc.send_to_thromer('stuff happened', '\n'.join(messages))
        for message in messages:
            metadata = cast(dict[str, Any], blob.metadata)
            pc.league_chat('%s [Day %s]' % (message, metadata['day']), trailing_whitespace=int(metadata['year']) % 5)
    
@app.route('/', methods=['POST'])
def process_box_score_eventarc():
    process_box_score(from_http(
        flask.request.headers,  # type: ignore[reportArgumentType]
        flask.request.get_data()))
    return "process_box_score done\n"
