#!/usr/bin/env python3

# TODO: once stable, deploy with retry on failure (in general)
# TODO: verify that the info in the box score matches (teams, runs)
# TODO: combine with analyze (saves gcs download cost)

# listen for writes to mydb indicating that a new box score is available,
# and dump the raw box score into cloud storage

# TODO: optional: retries
# TODO: combine with no-hitter etc analyzer
#

# Pennant Chase box score scraper

# Just throw box scores into files (cloud?) for later processing
# Someday make up a db (or nosql) schema and populate a cloud sql (?) instance and share
# it

import gzip
import re
import sys
from http import HTTPStatus
from typing import TYPE_CHECKING, cast

import flask
import google.cloud.exceptions
import requests
from cloudevents.core.bindings.http import HTTPMessage, from_http_event
from google.cloud.storage import Bucket
from google.cloud.storage import Client as StorageClient
from google.events.cloud import firestore


if TYPE_CHECKING:
    from cloudevents.core.base import BaseCloudEvent


BUCKET = "pc256-box-scores"
CONTENT_TYPE = "text/html; charset=utf-8"

app = flask.Flask(__name__)


def pubsub_to_gcs(event: BaseCloudEvent) -> flask.Response:
    """Triggered by a change to a Firestore document."""
    data = event.get_data()
    if not isinstance(data, bytes):
        msg = f"Firestore type is {type(data)}, should be bytes"
        print(msg)
        return flask.Response(status=HTTPStatus.BAD_REQUEST, response=msg)
    firestore_payload = cast(
        firestore.DocumentEventData, firestore.DocumentEventData.deserialize(data)
    )
    v = firestore_payload.value
    if not v:
        msg = "Value not present in payload, presumably a deletion request"
        print(msg)
        return flask.Response(status=HTTPStatus.OK, response=msg)
    data_map: dict[str, str] = {}
    for k in ("away_r", "home_r", "day", "year"):
        data_map[k] = str(v.fields[k].integer_value)
    for k in ("away", "home"):
        data_map[k] = v.fields[k].string_value
    print("data_map", data_map)
    firestore_path = event.get_extension("document")  # pyright: ignore[reportAny]
    if not isinstance(firestore_path, str):
        msg = "firestore path missing"
        print(msg)
        return flask.Response(status=HTTPStatus.BAD_REQUEST, response=msg)
    m = re.match(r".*/([^/]+)", firestore_path)
    if m is None:
        msg = f"Invalid firestore_path {firestore_path}"
        print(msg)
        return flask.Response(status=HTTPStatus.BAD_REQUEST, response=msg)
    game_id = cast(str, m[1])
    print(f"{game_id=}")

    # Get the cloud storage bucket.
    # If the bucket doesn't exists, fail, it is expensive
    # to repeatedly and redundantly call get_bucket.
    storage_client = StorageClient()
    bucket = Bucket(storage_client, BUCKET)

    box_score_url = (
        f"https://www.pennantchase.com/lgBoxScoreReader.aspx?sid={game_id}&lgid=256"
    )
    blob_name = game_id
    # Don't bother: when compressed: append .zstd
    # Don't bother: when compressed: upload zstd-dictionary-<id> if it is missing!
    # Don't bother: to compress: see examples/training/dictionary
    # TODONE if generation == 0 thingie
    blob = bucket.blob(blob_name)

    # Using request preconditions will result in duplicate downloads
    # from pennantchase.com in the case where we get duplicate
    # invocations from the Firestore trigger. I think it will be rare.
    # If it isn't then we should figure out why -- I neither want
    # to pay for successful blob.exists() calls, nor do I want to
    # double my load on pennantchase.com. Unsuccessful blob.exists()
    # calls are not billed, per https://cloud.google.com/storage/pricing:
    #
    # "Generally, you are not charged for operations that return 307,
    # 4xx, or 5xx responses. The exception is 404 responses returned by
    # buckets with Website Configuration enabled and the NotFoundPage
    # property set to a public object in that bucket."

    # grab box score (raw) and compress
    box_score = gzip.compress(requests.get(box_score_url, timeout=60).content)
    blob.metadata = data_map
    blob.content_encoding = "gzip"
    try:
        # Unnecessary: when compressed: content_type = 'application/octet-stream'
        blob.upload_from_string(
            box_score, content_type=CONTENT_TYPE, if_generation_match=0
        )
        print(f"uploaded {blob_name}", file=sys.stdout)
    except google.cloud.exceptions.PreconditionFailed:
        print(f"already uploaded {blob_name}", file=sys.stdout)
    except google.cloud.exceptions.NotFound:
        msg = f"Please create bucket gs://{BUCKET}"
        raise RuntimeError(msg) from None
    return flask.Response(status=HTTPStatus.OK, response="Uploaded to GCS")


@app.route("/", methods=["POST"])
def pubsub_to_gcs_eventarc() -> flask.Response:
    message = HTTPMessage(
        headers=dict(flask.request.headers), body=flask.request.get_data()
    )
    event = from_http_event(message)
    nominal_response = pubsub_to_gcs(event)
    if 400 <= nominal_response.status_code < 500:  # noqa: PLR2004
        return flask.Response(
            status=HTTPStatus.OK, response=nominal_response.get_data()
        )
    return nominal_response
