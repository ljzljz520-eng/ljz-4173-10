"""S3 存储封装. 测试通过 mock apps.media.s3.get_storage 替换."""
import boto3
from django.conf import settings


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
    )


class S3VideoStorage:
    def __init__(self, client=None, bucket=None):
        self.client = client or get_s3_client()
        self.bucket = bucket or settings.AWS_STORAGE_BUCKET_NAME

    def create_multipart(self, key, content_type):
        resp = self.client.create_multipart_upload(
            Bucket=self.bucket, Key=key, ContentType=content_type
        )
        return resp["UploadId"]

    def presign_part(self, key, upload_id, part_number, expires=None):
        return self.client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=expires or settings.VIDEO_PRESIGN_EXPIRES,
        )

    def complete_multipart(self, key, upload_id, parts):
        return self.client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )

    def abort_multipart(self, key, upload_id):
        return self.client.abort_multipart_upload(
            Bucket=self.bucket, Key=key, UploadId=upload_id
        )

    def presign_get(self, key, expires=None, download=False):
        params = {"Bucket": self.bucket, "Key": key}
        if download:
            params["ResponseContentDisposition"] = "attachment"
        return self.client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires or settings.VIDEO_PRESIGN_EXPIRES,
        )

    def head_object(self, key):
        return self.client.head_object(Bucket=self.bucket, Key=key)

    def delete_object(self, key):
        return self.client.delete_object(Bucket=self.bucket, Key=key)


_storage = None


def get_storage():
    global _storage
    if _storage is None:
        _storage = S3VideoStorage()
    return _storage
