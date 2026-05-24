"""Eventarc Firestore Curl Command Generator.

Generates curl commands for google.cloud.firestore.document.v1.written events
"""

import argparse
import base64
import json
import uuid
from datetime import UTC, datetime
from typing import cast

from google.events.cloud.firestore import DocumentEventData
from google.protobuf.timestamp_pb2 import Timestamp


type PrimitiveValue = str | int | float | bool
type FieldValue = PrimitiveValue | dict[str, FieldValue] | list[PrimitiveValue]
type Fields = dict[str, FieldValue]


def generate_event_id() -> str:
    """Generate a unique event ID."""
    return str(uuid.uuid4())


def get_timestamp() -> str:
    """Get current timestamp in RFC3339 format."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def create_document_fields(fields: Fields) -> dict[str, object]:  # noqa: C901
    """Convert simple fields to Firestore document format."""
    firestore_fields: dict[str, object] = {}

    for key, value in fields.items():
        if isinstance(value, str):
            firestore_fields[key] = {"stringValue": value}
        elif isinstance(value, bool):
            firestore_fields[key] = {"booleanValue": value}
        elif isinstance(value, int):
            firestore_fields[key] = {"integerValue": str(value)}
        elif isinstance(value, float):
            firestore_fields[key] = {"doubleValue": value}
        elif isinstance(value, dict):
            firestore_fields[key] = {
                "mapValue": {"fields": create_document_fields(value)}
            }
        else:
            array_values: list[dict[str, object]] = []
            for item in value:
                if isinstance(item, str):
                    array_values.append({"stringValue": item})
                elif isinstance(item, bool):
                    array_values.append({"booleanValue": item})
                elif isinstance(item, int):
                    array_values.append({"integerValue": str(item)})
                else:
                    array_values.append({"doubleValue": item})
            firestore_fields[key] = {"arrayValue": {"values": array_values}}

    return firestore_fields


def create_cloudevent_json(  # noqa: PLR0913
    project_id: str,
    database_id: str,
    collection_path: str,
    document_id: str,
    document_fields: Fields,
    deleted: bool,  # noqa: FBT001
) -> dict[str, object]:
    """Create CloudEvent structure for Firestore written event."""
    event_id = generate_event_id()
    timestamp = get_timestamp()
    document_path = (
        f"projects/{project_id}/databases/{database_id}/"
        f"documents/{collection_path}/{document_id}"
    )

    return {
        "specversion": "1.0",
        "id": event_id,
        "source": (
            f"//firestore.googleapis.com/projects/{project_id}/databases/{database_id}"
        ),
        "type": "google.cloud.firestore.document.v1.written",
        "datacontenttype": "application/json",
        "subject": f"documents/{collection_path}/{document_id}",
        "time": timestamp,
        "data": {
            "old_value" if deleted else "value": {
                "name": document_path,
                "fields": create_document_fields(document_fields),
                "createTime": timestamp,
                "updateTime": timestamp,
            },
            "updateMask": {},
        },
    }


def create_cloudevent_protobuf(  # noqa: PLR0913
    project_id: str,
    database_id: str,
    collection_path: str,
    document_id: str,
    document_fields: Fields,
    deleted: bool,  # noqa: FBT001
) -> str:
    """Make base64-encoded protobuf google.events.cloud.firestore.DocumentEventData."""
    # Create timestamp
    now = datetime.now(tz=UTC)
    timestamp = Timestamp()
    timestamp.FromDatetime(now)

    # Create document path
    document_path = (
        f"projects/{project_id}/databases/{database_id}/"
        f"documents/{collection_path}/{document_id}"
    )

    # Convert fields to Firestore Value objects
    firestore_values: dict[str, dict[str, object]] = {}
    for key, value in document_fields.items():
        if isinstance(value, str):
            firestore_values[key] = {"string_value": value}
        elif isinstance(value, bool):
            firestore_values[key] = {"boolean_value": value}
        elif isinstance(value, int):
            firestore_values[key] = {"integer_value": value}
        elif isinstance(value, float):
            firestore_values[key] = {"double_value": value}
        else:
            msg = f"Can't handle {key}={value}"
            raise TypeError(msg)

    val = {
        "name": document_path,  # f"{collection_path}/{document_id}",
        "fields": firestore_values,
    }
    if deleted:
        event_data = DocumentEventData(old_value=val)
    else:
        event_data = DocumentEventData(value=val)

    # Serialize to protobuf bytes and encode as base64
    protobuf_bytes = DocumentEventData.serialize(event_data)  # pyright: ignore[reportUnknownMemberType]
    return base64.b64encode(protobuf_bytes).decode("utf-8")


def generate_curl_command(  # noqa: PLR0913
    target_url: str,
    project_id: str,
    database_id: str,
    collection_path: str,
    document_id: str,
    location: str,
    document_fields: Fields,
    deleted: bool = False,  # noqa: FBT001, FBT002
    use_protobuf: bool = False,  # noqa: FBT001, FBT002
) -> str:
    """Generate curl command for Firestore written event."""
    event_id = generate_event_id()
    timestamp = get_timestamp()
    source = f"//firestore.googleapis.com/projects/{project_id}/databases/{database_id}"
    subject = f"documents/{collection_path}/{document_id}"

    # Common headers
    headers = [
        '-H "Ce-Specversion: 1.0"',
        '-H "Ce-Type: google.cloud.firestore.document.v1.written"',
        f'-H "Ce-Source: {source}"',
        f'-H "Ce-Id: {event_id}"',
        f'-H "Ce-Time: {timestamp}"',
        f'-H "Ce-Subject: {subject}"',
        f'-H "Ce-Project: {project_id}"',
        f'-H "Ce-Database: {database_id}"',
        f'-H "Ce-Document: {collection_path}/{document_id}"',
        f'-H "Ce-Location: {location}"',
    ]

    if use_protobuf:
        # Protobuf version
        headers.append('-H "Content-Type: application/protobuf"')
        headers.append('-H "Ce-Datacontenttype: application/protobuf"')

        protobuf_data = create_cloudevent_protobuf(
            project_id,
            database_id,
            collection_path,
            document_id,
            document_fields,
            deleted,
        )

        headers_str = " \\\n  ".join(headers)
        curl_cmd = f"""curl '{target_url}' \\
  {headers_str} \\
  --data-binary @<(echo '{protobuf_data}' | base64 -d)"""
    else:
        # JSON version
        headers.append('-H "Content-Type: application/json"')
        headers.append('-H "Ce-Datacontenttype: application/json"')

        event_data = create_cloudevent_json(
            project_id,
            database_id,
            collection_path,
            document_id,
            document_fields,
            deleted,
        )
        json_data = json.dumps(event_data, separators=(",", ":")).replace("'", r"\'")

        headers_str = " \\\n  ".join(headers)
        curl_cmd = f"""curl '{target_url}' \\
  {headers_str} \\
  -d $'{json_data}'"""

    return curl_cmd


def parse_fields(fields_str: str) -> Fields:
    """Parse fields from command line argument."""
    if not fields_str:
        return {
            "message": "Hello from Firestore!",
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }

    try:
        return cast(Fields, json.loads(fields_str))
    except json.JSONDecodeError:
        # Simple key=value parsing as fallback
        fields = {}
        for pair in fields_str.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                # Try to infer type
                if value.lower() in ("true", "false"):
                    fields[key.strip()] = value.lower() == "true"
                elif value.isdigit():
                    fields[key.strip()] = int(value)
                elif value.replace(".", "").isdigit():
                    fields[key.strip()] = float(value)
                else:
                    fields[key.strip()] = value
        return fields or {"message": "Hello from Firestore!"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate curl commands for Eventarc Firestore written events",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python %(prog)s --url http://localhost:8080

  # Custom document
  python %(prog)s --url http://localhost:8080 --collection users --document user123

  # With custom fields (JSON)
  python %(prog)s --url http://localhost:8080 --fields '{"name":"John","age":30}'

  # With custom fields (key=value)
  python %(prog)s --url http://localhost:8080 --fields 'name=John,age=30,active=true'

  # Protobuf format
  python %(prog)s --url http://localhost:8080 --protobuf

  # Full example
  python %(prog)s \\
    --url https://my-function-url.cloudfunctions.net \\
    --project my-project \\
    --collection orders \\
    --document order-456 \\
    --fields '{"total":99.99,"status":"pending","items":["item1","item2"]}'
        """,
    )

    _ = parser.add_argument(
        "--url", default="http://localhost:8080", help="Target URL for the POST request"
    )
    _ = parser.add_argument(
        "--project", default="pennantchase-256-dev", help="GCP Project ID"
    )
    _ = parser.add_argument(
        "--location", default="us-central1", help="GCP location/region"
    )
    _ = parser.add_argument(
        "--database", default="'(default)'", help="Firestore database ID"
    )
    _ = parser.add_argument("--collection", default="mydb", help="Collection path")
    _ = parser.add_argument("--document", default="doc123", help="Document ID")
    _ = parser.add_argument(
        "--fields",
        default=(
            '{"year": 2054, "away_r": 3, "day": 182, '
            '"home": "256-3", "away": "256-15", "home_r": 4}'
        ),
        help="Document fields as JSON string or key=value pairs",
    )
    _ = parser.add_argument(
        "--deleted",
        action="store_true",
        help="Generate payload corresponding to a deleted document",
    )
    _ = parser.add_argument(
        "--protobuf",
        action="store_true",
        help="Generate protobuf format instead of JSON",
    )

    args = parser.parse_args()

    # Parse document fields
    document_fields = parse_fields(cast(str, args.fields))

    # Generate curl command
    curl_command = generate_curl_command(
        target_url=cast(str, args.url),
        project_id=cast(str, args.project),
        database_id=cast(str, args.database),
        collection_path=cast(str, args.collection),
        document_id=cast(str, args.document),
        document_fields=document_fields,
        location=cast(str, args.location),
        deleted=cast(bool, args.deleted),
        use_protobuf=cast(bool, args.protobuf),
    )

    print(curl_command)


if __name__ == "__main__":
    main()
