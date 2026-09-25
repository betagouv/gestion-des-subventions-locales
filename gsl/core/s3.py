import boto3
from django.conf import settings

from gsl.core.exceptions import Http404


def get_s3_object(file_name):
    s3 = get_s3_client()
    bucket = settings.AWS_STORAGE_BUCKET_NAME

    try:
        return s3.get_object(Bucket=bucket, Key=file_name)
    except s3.exceptions.NoSuchKey:
        raise Http404(user_message="Fichier non trouvé")


def get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
    )
