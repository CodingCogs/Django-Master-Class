# shop/management/commands/init_storage.py
import json

from botocore.exceptions import ClientError
from django.conf import settings
from django.core.files.storage import storages
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the media bucket (if missing) and allow public reads of media/."

    def handle(self, *args, **options):
        if not settings.USE_S3:
            self.stdout.write("USE_S3 is off; using the local filesystem. Nothing to do.")
            return

        storage = storages["default"]
        client = storage.connection.meta.client
        bucket = storage.bucket_name

        try:
            client.head_bucket(Bucket=bucket)
            self.stdout.write(f"Bucket '{bucket}' already exists.")
        except ClientError:
            client.create_bucket(Bucket=bucket)
            self.stdout.write(self.style.SUCCESS(f"Created bucket '{bucket}'."))

        policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/{storage.location}/*"],
            }],
        }
        client.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
        self.stdout.write(f"Public read enabled for {bucket}/{storage.location}/*")
