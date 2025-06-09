#!/usr/bin/env python3
"""
Eventarc Firestore Curl Command Generator
Generates curl commands for google.cloud.firestore.document.v1.written events
"""

import json
import uuid
import base64
import argparse
from datetime import datetime, timezone
from typing import Dict, Any
from google.events.cloud.firestore import DocumentEventData
from google.protobuf.timestamp_pb2 import Timestamp
from datetime import datetime


def generate_event_id() -> str:
    """Generate a unique event ID"""
    return str(uuid.uuid4())


def get_timestamp() -> str:
    """Get current timestamp in RFC3339 format"""
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def create_document_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Convert simple fields to Firestore document format"""
    firestore_fields = {}
    
    for key, value in fields.items():
        if isinstance(value, str):
            firestore_fields[key] = {"stringValue": value}
        elif isinstance(value, int):
            firestore_fields[key] = {"integerValue": str(value)}
        elif isinstance(value, float):
            firestore_fields[key] = {"doubleValue": value}
        elif isinstance(value, bool):
            firestore_fields[key] = {"booleanValue": value}
        elif isinstance(value, dict):
            firestore_fields[key] = {"mapValue": {"fields": create_document_fields(value)}}
        elif isinstance(value, list):
            array_values = []
            for item in value:
                if isinstance(item, str):
                    array_values.append({"stringValue": item})
                elif isinstance(item, int):
                    array_values.append({"integerValue": str(item)})
                elif isinstance(item, float):
                    array_values.append({"doubleValue": item})
                elif isinstance(item, bool):
                    array_values.append({"booleanValue": item})
                else:
                    array_values.append({"stringValue": str(item)})
            firestore_fields[key] = {"arrayValue": {"values": array_values}}
        else:
            firestore_fields[key] = {"stringValue": str(value)}
    
    return firestore_fields


def create_cloudevent_json(project_id: str, database_id: str, collection_path: str, 
                          document_id: str, document_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Create CloudEvent structure for Firestore written event"""
    event_id = generate_event_id()
    timestamp = get_timestamp()
    document_path = f"projects/{project_id}/databases/{database_id}/documents/{collection_path}/{document_id}"
    
    return {
        "specversion": "1.0",
        "id": event_id,
        "source": f"//firestore.googleapis.com/projects/{project_id}/databases/{database_id}",
        "type": "google.cloud.firestore.document.v1.written",
        "datacontenttype": "application/json",
        "subject": f"documents/{collection_path}/{document_id}",
        "time": timestamp,
        "data": {
            "value": {
                "name": document_path,
                "fields": create_document_fields(document_fields),
                "createTime": timestamp,
                "updateTime": timestamp
            },
            "updateMask": {}
        }
    }


def create_protobuf_placeholder(project_id: str, database_id: str, collection_path: str, 
                               document_id: str, document_fields: Dict[str, Any]) -> str:
    """Create base64-encoded protobuf using google.events.cloud.firestore.DocumentEventData"""
    # Create timestamp
    now = datetime.now()
    timestamp = Timestamp()
    timestamp.FromDatetime(now)
    
    # Create document path
    # document_path = f"projects/{project_id}/databases/{database_id}/documents/{collection_path}/{document_id}"
    
    # Convert fields to Firestore Value objects
    firestore_values = {}
    for key, value in document_fields.items():
        if isinstance(value, str):
            firestore_values[key] = {"string_value": value}
        elif isinstance(value, int):
            firestore_values[key] = {"integer_value": value}
        elif isinstance(value, float):
            firestore_values[key] = {"double_value": value}
        elif isinstance(value, bool):
            firestore_values[key] = {"boolean_value": value}
        else:
            raise Exception(f"Can't handle {key}={value}")
    
    event_data = DocumentEventData(value={
        "name": f"{collection_path}/{document_id}",
        "fields": firestore_values
    })
    
    # Serialize to protobuf bytes and encode as base64
    protobuf_bytes = event_data.SerializeToString()
    return base64.b64encode(protobuf_bytes).decode('utf-8')


def generate_curl_command(target_url: str, project_id: str, database_id: str, 
                         collection_path: str, document_id: str, 
                         document_fields: Dict[str, Any], use_protobuf: bool = False) -> str:
    """Generate curl command for Firestore written event"""
    
    event_id = generate_event_id()
    timestamp = get_timestamp()
    source = f"//firestore.googleapis.com/projects/{project_id}/databases/{database_id}"
    subject = f"documents/{collection_path}/{document_id}"
    
    # Common headers
    headers = [
        f'-H "Ce-Specversion: 1.0"',
        f'-H "Ce-Type: google.cloud.firestore.document.v1.written"',
        f'-H "Ce-Source: {source}"',
        f'-H "Ce-Id: {event_id}"',
        f'-H "Ce-Time: {timestamp}"',
        f'-H "Ce-Subject: {subject}"'
    ]
    
    if use_protobuf:
        # Protobuf version
        headers.append('-H "Content-Type: application/protobuf"')
        headers.append('-H "Ce-Datacontenttype: application/protobuf"')
        
        protobuf_data = create_protobuf_placeholder(project_id, database_id, collection_path, document_id, document_fields)
        
        headers_str = ' \\\n  '.join(headers)
        curl_cmd = f"""curl -X POST '{target_url}' \\
  {headers_str} \\
  --data-binary @<(echo '{protobuf_data}' | base64 -d)"""
    else:
        # JSON version
        headers.append('-H "Content-Type: application/json"')
        headers.append('-H "Ce-Datacontenttype: application/json"')
        
        event_data = create_cloudevent_json(project_id, database_id, collection_path, document_id, document_fields)
        json_data = json.dumps(event_data, separators=(',', ':'))
        
        headers_str = ' \\\n  '.join(headers)
        curl_cmd = f"""curl -X POST '{target_url}' \\
  {headers_str} \\
  -d '{json_data}'"""
    
    return curl_cmd


def parse_fields(fields_str: str) -> Dict[str, Any]:
    """Parse fields from command line argument"""
    if not fields_str:
        return {"message": "Hello from Firestore!", "timestamp": datetime.now().isoformat()}
    
    try:
        return json.loads(fields_str)
    except json.JSONDecodeError:
        # Simple key=value parsing as fallback
        fields = {}
        for pair in fields_str.split(','):
            if '=' in pair:
                key, value = pair.split('=', 1)
                # Try to infer type
                if value.lower() in ('true', 'false'):
                    fields[key.strip()] = value.lower() == 'true'
                elif value.isdigit():
                    fields[key.strip()] = int(value)
                elif value.replace('.', '').isdigit():
                    fields[key.strip()] = float(value)
                else:
                    fields[key.strip()] = value
        return fields if fields else {"message": "Hello from Firestore!"}


def main():
    # event_data = DocumentEventData(
    #     value={
    #         "name": "mydoc",
    #         "fields": {
    #             "f1": {"string_value": "field1"},
    #             "f2": {"integer_value": 37}
    #         }
    #     }
    # )
    # raise Exception(f"{event_data=}")
    # document = Document(
    #     name="mydoc",
    #     fields={
    #         "f1": Value(string_value="field1"),
    #         "f2": Value(integer_value=37)
    #     }
    # )
    # event_data = DocumentEventData(value=document)
    # raise Exception(f"{event_data=}")
    # doc = Document()
    # doc.name = "mydoc"
    # doc.fields["f1"].string_value = "field1"
    # doc.fields["f2"].integer_value = 37

    # # Wrap it in DocumentEventData
    # event_data = DocumentEventData(value=doc)
    # print(f"THROMER {event_data=}")
    # raise Exception("byebye")
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
  python %(prog)s --url http://localhost:8080 --fields '{"name":"John","age":30,"active":true}'

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
        """
    )
    
    parser.add_argument("--url", default="http://localhost:8080", help="Target URL for the POST request")
    parser.add_argument("--project", default="pennantchase-256", help="GCP Project ID (default: demo-project)")
    parser.add_argument("--database", default="db-us-west1", help="Firestore database ID (default: (default))")
    parser.add_argument("--collection", default="mydb", help="Collection path (default: documents)")
    parser.add_argument("--document", default="doc123", help="Document ID (default: doc123)")
    parser.add_argument("--fields", default='{"year": 2054, "away_r": 3, "day": 182, "home": "256-3", "away": "256-15", "home_r": 4}', help="Document fields as JSON string or key=value pairs")
    parser.add_argument("--protobuf", action="store_true", help="Generate protobuf format instead of JSON")
    
    args = parser.parse_args()
    
    # Parse document fields
    document_fields = parse_fields(args.fields)
    
    # Generate curl command
    curl_command = generate_curl_command(
        target_url=args.url,
        project_id=args.project,
        database_id=args.database,
        collection_path=args.collection,
        document_id=args.document,
        document_fields=document_fields,
        use_protobuf=args.protobuf
    )
    
    print(curl_command)


if __name__ == "__main__":
    main()

# for example
"""
"chase_handle_event flask.request.headers=EnvironHeaders([('Host', 'unified-service-u7x6iclp7a-uw.a.run.app'), ('Content-Type', 'application/protobuf'), ('Authorization', 'Bearer ELIDED'), ('Content-Length', '546'), ('Accept', 'application/json'), ('From', 'noreply@google.com'), ('User-Agent', 'APIs-Google; (+https://developers.google.com/webmasters/APIs-Google.html)'), ('X-Cloud-Trace-Context', 'a9e38a2b7936e87ec6194e47c87d9d67/13923462220437292968'), ('X-Forwarded-Proto', 'https'), ('Traceparent', '00-a9e38a2b7936e87ec6194e47c87d9d67-c13a131eacbc87a8-00'), ('X-Forwarded-For', '66.249.84.161'), ('Forwarded', 'for="66.249.84.161";proto=https'), ('Accept-Encoding', 'gzip, deflate, br'), ('Ce-Specversion', '1.0'), ('Ce-Id', '8fc0fdf1-b1bd-4874-a938-3ae26935102b'), ('Ce-Time', '2025-06-09T23:03:23.018239Z'), ('Ce-Database', '(default)'), ('Ce-Source', '//firestore.googleapis.com/projects/ynab-sheets-001/databases/(default)'), ('Ce-Document', 'chase-data/amazon-orders/amazon-orders/111-2051511-4394609'), ('Ce-Dataschema', 'https://github.com/googleapis/google-cloudevents/blob/main/proto/google/events/cloud/firestore/v1/data.proto'), ('Ce-Project', 'ynab-sheets-001'), ('Ce-Type', 'google.cloud.firestore.document.v1.written'), ('Ce-Namespace', '(default)'), ('Ce-Location', 'us-west1'), ('Ce-Subject', 'documents/chase-data/amazon-orders/amazon-orders/111-2051511-4394609')]) flask.request.get_data()=b'\n\x9f\x04\nqprojects/ynab-sheets-001/databases/(default)/documents/chase-data/amazon-orders/amazon-orders/111-2051511-4394609\x12\x14\n\x08max_date\x12\x08R\x06\x08\x80\xf6\xf8\xc1\x06\x12\xec\x02\n\x07details\x12\xe0\x02J\xdd\x02\n\xda\x022\xd7\x02\n\xf5\x01\n\nitem_lines\x12\xe6\x01J\xe3\x01\n\xe0\x012\xdd\x01\n\x0b\n\x05count\x12\x02\x10\x01\n\x17\n\x10item_price_cents\x12\x03\x10\xe6\x07\n\xb4\x01\n\x0bdescription\x12\xa4\x01\x8a\x01\xa0\x01BOENZONE Nut & Bolt Thread Checker (Complete SAE/Inch and Metric Set) - 26 Male/Female Gauges 14 Inch 12 Quickly Checking Nuts Bolts or Verifying The Size Pitch\n]\n\x0btransaction\x12N2L\n%\n\x0bdescription\x12\x16\x8a\x01\x13Visa ending in 7262\n\x15\n\x04date\x12\r\x8a\x01\n2025-06-03\n\x0c\n\x05cents\x12\x03\x10\xa4\x08\x12\x0b\n\x03who\x12\x04\x8a\x01\x01s\x1a\x0b\x08\xbb\xd0\x9d\xc2\x06\x10\x98\x9c\xd9\x08"\x0b\x08\xbb\xd0\x9d\xc2\x06\x10\x98\x9c\xd9\x08'"
timestamp: "2025-06-09T23:03:29.059372Z"
"""

"""
"chase_handle_event event.get_attributes()=mappingproxy({'specversion': '1.0', 'id': 'c6d9e1b3-69d0-4306-812f-2cb5b0dab064', 'source': '//firestore.googleapis.com/projects/ynab-sheets-001/databases/(default)', 'type': 'google.cloud.firestore.document.v1.written', 'datacontenttype': 'application/protobuf', 'dataschema': 'https://github.com/googleapis/google-cloudevents/blob/main/proto/google/events/cloud/firestore/v1/data.proto', 'subject': 'documents/chase-data/amazon-orders/amazon-orders/111-2051511-4394609', 'time': '2025-06-09T23:03:22.918895Z', 'database': '(default)', 'document': 'chase-data/amazon-orders/amazon-orders/111-2051511-4394609', 'namespace': '(default)', 'project': 'ynab-sheets-001', 'location': 'us-west1'}) event.data=b'\x12\xa1\x04\nqprojects/ynab-sheets-001/databases/(default)/documents/chase-data/amazon-orders/amazon-orders/111-2051511-4394609\x12\x14\n\x08max_date\x12\x08R\x06\x08\x80\xf6\xf8\xc1\x06\x12\xec\x02\n\x07details\x12\xe0\x02J\xdd\x02\n\xda\x022\xd7\x02\n\xf5\x01\n\nitem_lines\x12\xe6\x01J\xe3\x01\n\xe0\x012\xdd\x01\n\x0b\n\x05count\x12\x02\x10\x01\n\x17\n\x10item_price_cents\x12\x03\x10\xe6\x07\n\xb4\x01\n\x0bdescription\x12\xa4\x01\x8a\x01\xa0\x01BOENZONE Nut & Bolt Thread Checker (Complete SAE/Inch and Metric Set) - 26 Male/Female Gauges 14 Inch 12 Quickly Checking Nuts Bolts or Verifying The Size Pitch\n]\n\x0btransaction\x12N2L\n\x0c\n\x05cents\x12\x03\x10\xa4\x08\n\x15\n\x04date\x12\r\x8a\x01\n2025-06-03\n%\n\x0bdescription\x12\x16\x8a\x01\x13Visa ending in 7262\x12\x0b\n\x03who\x12\x04\x8a\x01\x01s\x1a\x0c\x08\xc2\xdc\x8f\xc2\x06\x10\x98\xa5\xb7\xb6\x02"\x0c\x08\xc2\xdc\x8f\xc2\x06\x10\x98\xa5\xb7\xb6\x02' firestore_payload=old_value {"
"""

# firestore_payload.value.name='projects/ynab-sheets-001/databases/(default)/documents/chase-data/amazon-orders/amazon-orders/111-2051511-4394609'
