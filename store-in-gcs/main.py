#!/usr/bin/env python3

# TODO once stable, deploy with retry on failure (in general)
# TODO verify that the info in the box score matches (teams, runs)
# TODO combine with analyze (saves gcs download cost)

# gcloud --project pennantchase-256 functions deploy pubsub_to_gcs --gen2 --region us-central1 --runtime python312 --trigger-location nam5 --trigger-event-filters=database='(default)' --trigger-event-filters document='mydb/{username}'  --trigger-event-filters type=google.cloud.firestore.document.v1.written

# listen for writes to mydb indicating that a new box score is available,
# and dump the raw box score into cloud storage

# TODO
#  optional: retries
#  combine with no-hitter etc analyzer
#  

# Pennant Chase box score scraper

# Just throw box scores into files (cloud?) for later processing
# Someday make up a db (or nosql) schema and populate a cloud sql (?) instance and share it

import argparse
import bs4
import csv
import json
import os
import pprint
import re
import requests
import sys
import time

from google.cloud import exceptions, storage

if ('GOOGLE_APPLICATION_CREDENTIALS' not in os.environ and
    'FUNCTION_TARGET' not in os.environ and
    'FUNCTION_TRIGGER_TYPE' not in os.environ and
    ('CLOUD_SHELL' not in os.environ or not os.environ['CLOUD_SHELL'])):
  os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../service-account-key.json'

BUCKET = 'pc256-box-scores'
CONTENT_TYPE = 'text/html; charset=utf-8'

def pubsub_to_gcs(data, context):
  """ Triggered by a change to a Firestore document.
  Args:
      data (dict): The event payload.
      context (google.cloud.functions.Context): Metadata for the event.
  """
  trigger_resource = context.resource
  print('Function triggered by change to: %s' % trigger_resource)
  # print(('data',data))
  # print(('context',context))

  # print('\nOld value:')
  # print(json.dumps(data["oldValue"]))
  
  # print('\nNew value:')
  print('data["value"]', data["value"])

  # {"createTime": "2021-01-27T05:17:54.788479Z", "fields": {"away": {"stringValue": "50ebd2f2-ba59-4378-ac40-66e11a258087"}, "away_r": {"stringValue": "6"}, "day": {"integerValue": "65"}, "home": {"stringValue": "9de82fcb-d4c8-4ff7-a4a4-36bc69394bc0"}, "home_r": {"stringValue": "7"}, "year": {"integerValue": "2039"}}, "name": "projects/pennantchase-256/databases/(default)/documents/mydb/000-delete-this-too-ghCRslHH9Mio2Rc2sM000", "updateTime": "2021-01-27T05:17:54.788479Z"}
  data_map = {}
  for k in ('away_r','home_r','day','year'):
    data_map[k] = int(data['value']['fields'][k]['integerValue'])
  for k in ('away', 'home'):
    data_map[k] = data['value']['fields'][k]['stringValue']
  game_id = re.match(r'.*/documents/mydb/(.*)', data['value']['name'])[1]
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
  # when compressed: append .zstd
  # when compressed: upload zstd-dictionary-<id> if it is missing!
  # to compress: see examples/training/dictionary
  # TODONE if generation == 0 thingie
  blob = bucket.blob(blob_name)
  if not blob.exists():
    blob.metadata = data_map
    # grab box score (raw)
    box_score = requests.get(box_score_url).content
    # write to cloud
    blob.upload_from_string(box_score, content_type=CONTENT_TYPE, if_generation_match=0)
    # when compressed:
    # content_type = 'application/octet-stream'
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
  

