#!/usr/bin/env python3

# TODO: someday
#  don't send if the message is already in the chatbox
#  don't send if the game was more than a couple days ago
# TODO: also report the day
# TODO: would be nice to move to a subdirectory

import sys
from http import HTTPStatus
from typing import TYPE_CHECKING, cast

import flask
import google.cloud.exceptions
from cloudevents.core.bindings.http import HTTPMessage, from_http_event
from google.cloud.storage import Bucket
from google.cloud.storage import Client as StorageClient

from lib import analyze, pcweb


if TYPE_CHECKING:
    from cloudevents.core.base import BaseCloudEvent


app = flask.Flask(__name__)


def process_object(bucket_name: str, blob_name: str) -> list[pcweb.ChatEntry]:
    blob_label = f"gs://{bucket_name}/{blob_name}"
    print(blob_label)
    storage_client = StorageClient()
    bucket = Bucket(storage_client, bucket_name)
    blob = bucket.get_blob(blob_name)
    if blob is None:
        msg = f"{blob_label} not found"
        # This can happen, for example when we upload a random object to the bucket
        # while testing and then delete it.
        raise analyze.BoxscoreError(msg)
    if blob.metadata is None:
        msg = f"metadata missing from {blob_label}"
        raise RuntimeError(msg)
    if "day" not in blob.metadata or "year" not in blob.metadata:
        msg = f"day and/or year missing from {blob_label}"
        raise RuntimeError(msg)
    # # TODO: remove this after store-in-gcs has baked for a while
    # if blob_name.find("-replay") > 0:
    #     print("replay, skipping")
    #     return
    try:
        data = blob.download_as_text()
    except google.cloud.exceptions.NotFound as e:
        print(e)
        msg = f"Bucket or object not found gs://{bucket_name}/{blob_name}"
        raise RuntimeError(msg) from None
    messages = analyze.analyze(data)
    return [
        pcweb.ChatEntry(
            message=f"{message} [Day {blob.metadata['day']}]",
            trailing_whitespace=int(blob.metadata["year"]) % 5,
        )
        for message in messages
    ]


def process_box_score(event: BaseCloudEvent) -> flask.Response:
    data = event.get_data()
    if not isinstance(data, dict):
        msg = f"Cloud Storage message type is {type(data)}, should be dict"
        return flask.Response(status=HTTPStatus.BAD_REQUEST, response=msg)
    data = cast(dict[str, str], data)
    bucket_name = data["bucket"]
    blob_name = data["name"]
    entries = process_object(bucket_name, blob_name)
    if entries:
        pc = pcweb.PcWeb("256")  # '1000' for testing
        # pc.send_to_thromer('stuff happened', '\n'.join(messages))
        for entry in entries:
            pc.league_chat(entry)
    return flask.Response(status=HTTPStatus.OK, response="Processed box score")


@app.route("/", methods=["POST"])
def process_box_score_eventarc() -> flask.Response:
    message = HTTPMessage(
        headers=dict(flask.request.headers), body=flask.request.get_data()
    )
    event = from_http_event(message)
    nominal_response: flask.Response
    try:
        nominal_response = process_box_score(event)
    except analyze.BoxscoreError as e:
        nominal_response = flask.Response(
            status=HTTPStatus.BAD_REQUEST, response=str(e)
        )
    if 400 <= nominal_response.status_code < 500:  # noqa: PLR2004
        return flask.Response(
            status=HTTPStatus.OK, response=nominal_response.get_data()
        )
    return nominal_response


def main(argv: list[str]) -> None:
    for entry in process_object(argv[0], argv[1]):
        print(f"{entry.message=} {entry.trailing_whitespace=}")


if __name__ == "__main__":
    main(sys.argv[1:])
