#!/usr/bin/env python3

# TODO once stable, deploy with retry on failure (in general)
# TODO verify that the info in the box score matches (teams, runs)
# TODO combine with analyze (saves gcs download cost)

# listen for writes to mydb indicating that a new box score is available,
# and dump the raw box score into cloud storage

# TODO
#  optional: retries
#  combine with no-hitter etc analyzer
#  

# Pennant Chase box score scraper

# Just throw box scores into files (cloud?) for later processing
# Someday make up a db (or nosql) schema and populate a cloud sql (?) instance and share it

import gzip
import re
import sys

import flask
import requests
from cloudevents.http import from_http
from google.cloud import exceptions, storage
from google.events.cloud import firestore

BUCKET = 'pc256-box-scores'
CONTENT_TYPE = 'text/html; charset=utf-8'

app = flask.Flask(__name__)

def pubsub_to_gcs(event):
  """ Triggered by a change to a Firestore document.
  """
  # https://cloud.google.com/functions/docs/calling/cloud-firestore#example_1_hello_function
  firestore_payload = firestore.DocumentEventData()
  firestore_payload._pb.ParseFromString(event.data)

  # firestore_payload.value is a Document I guess https://cloud.google.com/python/docs/reference/firestore/1.4.0/document
  # type is here: https://github.com/googleapis/google-cloudevents-python/blob/main/src/google/events/cloud/firestore_v1/types/data.py#L58
  v = firestore_payload.value
  if not v:
    print("value not present in payload, presumably a deletion request")
    return
  # {"createTime": "2021-01-27T05:17:54.788479Z", "fields": {"away": {"stringValue": "50ebd2f2-ba59-4378-ac40-66e11a258087"}, "away_r": {"stringValue": "6"}, "day": {"integerValue": "65"}, "home": {"stringValue": "9de82fcb-d4c8-4ff7-a4a4-36bc69394bc0"}, "home_r": {"stringValue": "7"}, "year": {"integerValue": "2039"}}, "name": "projects/pennantchase-256/databases/(default)/documents/mydb/000-delete-this-too-ghCRslHH9Mio2Rc2sM000", "updateTime": "2021-01-27T05:17:54.788479Z"}

  data_map = {}
  for k in ('away_r','home_r','day','year'):
    data_map[k] = int(v.fields[k].integer_value)
  for k in ('away', 'home'):
    data_map[k] = v.fields[k].string_value
  game_id = re.match(r'.*/(.*)', event['document'])[1]
  print('data_map',data_map)
  print('game_id',game_id)

  # Get a cloud storage bucket
  storage_client = storage.Client()
  bucket = None
  try:
    bucket = storage_client.get_bucket(BUCKET)
  except exceptions.NotFound as e:
    bucket = storage.Bucket(storage_client, name=BUCKET)
    bucket.storage_class = 'ARCHIVE'
    bucket.create(location='US-WEST1')

  box_score_url = 'https://www.pennantchase.com/lgBoxScoreReader.aspx?sid=%s&lgid=256' % game_id
  blob_name = game_id
  # Don't bother: when compressed: append .zstd
  # Don't bother: when compressed: upload zstd-dictionary-<id> if it is missing!
  # Don't bother: to compress: see examples/training/dictionary
  # TODONE if generation == 0 thingie
  blob = bucket.blob(blob_name)
  if not blob.exists():
    blob.metadata = data_map
    # grab box score (raw) and compress
    box_score = gzip.compress(requests.get(box_score_url).content)
    blob.content_encoding = 'gzip'
    # write to cloud
    blob.upload_from_string(box_score, content_type=CONTENT_TYPE, if_generation_match=0)
    # Unnecessary: when compressed: content_type = 'application/octet-stream'
    print('uploaded %s' % blob_name, file=sys.stdout)
  else:
    print('already uploaded %s' % blob_name, file=sys.stdout)
  replay_url = 'https://www.pennantchase.com/lgReplay.aspx?lgid=256&sid=%s&hid=%s&vid=%s' % (game_id, data_map['home'], data_map['away'])
  replay_blob_name = game_id + '-replay'
  # TODO consider moving these to a different bucket so we can segregate Pub/Sub object creation messages.
  replay_blob = bucket.blob(replay_blob_name)
  if not replay_blob.exists():
    replay_blob.metadata = data_map
    # grab replay data
    replay = requests.get(replay_url).content
    # write to cloud
    replay_blob.upload_from_string(replay, content_type=CONTENT_TYPE, if_generation_match=0)
    # when compressed:
    # content_type = 'application/octet-stream'
    print('uploaded %s' % replay_blob_name, file=sys.stdout)
  else:
    print('already uploaded %s' % replay_blob_name, file=sys.stdout)

@app.route('/', methods=['POST'])
def pubsub_to_gcs_eventarc():
  pubsub_to_gcs(from_http(
    flask.request.headers,  # type: ignore[reportArgumentType]
    flask.request.get_data()))
  return "pubsub_to_gcs done\n"
