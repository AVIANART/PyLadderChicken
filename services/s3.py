import boto3


class S3Service:
    def __init__(self, endpoint_url, access_key, secret_key, bucket_name):
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        self.bucket_name = bucket_name

    def upload_file(self, file_path, object_name):
        try:
            self.s3_client.upload_file(file_path, self.bucket_name, object_name)
            return True
        except Exception as e:
            print(f"Error uploading file to S3: {e}")
            return False
