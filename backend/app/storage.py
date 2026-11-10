"""Private server-only artifacts; object keys are server-generated."""
import os
from pathlib import Path
def local_path(key):
    root = Path(os.getenv("ARTIFACT_DIR", "./artifacts")).resolve()
    target = (root / key).resolve()
    if not target.is_relative_to(root): raise ValueError("Invalid artifact key")
    return target
def put(key, data):
    if os.getenv("S3_BUCKET"):
        import boto3
        boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL") or None).put_object(
            Bucket=os.environ["S3_BUCKET"], Key=key, Body=data, ServerSideEncryption="AES256")
    else:
        p = local_path(key); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
def delete(key):
    if os.getenv("S3_BUCKET"):
        import boto3
        boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL") or None).delete_object(Bucket=os.environ["S3_BUCKET"], Key=key)
    else: local_path(key).unlink(missing_ok=True)

def get(key):
    if os.getenv("S3_BUCKET"):
        import boto3
        response = boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL") or None).get_object(
            Bucket=os.environ["S3_BUCKET"], Key=key)
        with response["Body"] as body:
            return body.read()
    return local_path(key).read_bytes()
