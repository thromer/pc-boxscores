#!/usr/bin/env python3

# TODO: someday
#  don't send if the message is already in the chatbox
#  don't send if the game was more than a couple days ago
# TODO: also report the day
# TODO: would be nice to move to a subdirectory

import sys
from typing import cast

import flask
from cloudevents.http import CloudEvent, from_http
from google.cloud import exceptions, storage

from lib import analyze, pcweb


app = flask.Flask(__name__)


def process_object(bucket_name: str, blob_name: str) -> list[pcweb.ChatEntry]:
    blob_label = f"gs://{bucket_name}/{blob_name}"
    print(blob_label)
    storage_client = storage.Client()
    bucket = storage.Bucket(storage_client, bucket_name)
    blob = bucket.get_blob(blob_name)
    if blob is None:
        msg = f"{blob_label} not found"
        raise RuntimeError(msg)
    if blob.metadata is None:
        msg = f"metadata missing from {blob_label}"
        raise RuntimeError(msg)
    metadata = cast(dict[str, str], blob.metadata)
    if "day" not in metadata or "year" not in metadata:
        msg = f"day and/or year missing from {blob_label}"
        raise RuntimeError(msg)
    # # TODO: remove this after store-in-gcs has baked for a while
    # if blob_name.find("-replay") > 0:
    #     print("replay, skipping")
    #     return
    try:
        data = blob.download_as_text()
    except exceptions.NotFound as e:
        print(e)
        msg = f"Bucket or object not found gs://{bucket_name}/{blob_name}"
        raise RuntimeError(msg) from None
    return [
        pcweb.ChatEntry(
            message=f"{message} [Day {metadata['day']}]",
            trailing_whitespace=int(metadata["year"]) % 5,
        )
        for message in analyze.analyze(data)
    ]


def process_box_score(event: CloudEvent) -> None:
    bucket_name = event.data["bucket"]
    blob_name = event.data["name"]
    entries = process_object(bucket_name, blob_name)
    if entries:
        pc = pcweb.PcWeb("256")  # '1000' for testing
        # pc.send_to_thromer('stuff happened', '\n'.join(messages))
        for entry in entries:
            pc.league_chat(entry)


@app.route("/", methods=["POST"])
def process_box_score_eventarc() -> str:
    process_box_score(
        from_http(
            flask.request.headers,  # type: ignore[reportArgumentType]
            flask.request.get_data(),
        )
    )
    return "process_box_score done\n"


def main(argv: list[str]) -> None:
    for entry in process_object(argv[0], argv[1]):
        print(f"{entry.message=} {entry.trailing_whitespace=}")


if __name__ == "__main__":
    main(sys.argv[1:])
