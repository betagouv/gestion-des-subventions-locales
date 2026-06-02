"""
Configure the S3 bucket for this app: CORS rules so the browser can upload
scans directly via a presigned POST (see `gsl_notification.views.import_views`),
plus lifecycle rules that expire temporary import and export objects.

Without a CORS rule allowing POST from the app origin, Scaleway/S3 answers the
browser's upload with a 403 that carries no `Access-Control-Allow-Origin`
header, which the browser reports as a cross-origin error.

Usage:
    python manage.py configure_s3_bucket --origin http://localhost:8000
    python manage.py configure_s3_bucket --origin https://turgot.example.gouv.fr
    python manage.py configure_s3_bucket   # https://<host> for each ALLOWED_HOSTS
    python manage.py configure_s3_bucket --show   # print the current rules

Run with no --origin from the deploy (postdeploy in the Procfile): the allowed
origins default to https://<host> for every entry in settings.ALLOWED_HOSTS, so
each environment configures its own bucket without a hardcoded host.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from gsl_notification.exports import EXPORT_PREFIX
from gsl_notification.models import DocumentImportJob
from gsl_notification.utils import get_s3_client

# Temporary import uploads are deleted at the end of a successful job; this
# lifecycle rule is the backstop that reaps objects orphaned by an abandoned
# upload (modal closed, job never started) and bounds the fill-the-bucket
# abuse vector. One day comfortably outlies the presigned POST's 1 h validity.
_IMPORT_LIFECYCLE_RULE = {
    "ID": "expire-temp-imports",
    "Filter": {"Prefix": DocumentImportJob.TEMP_S3_PREFIX},
    "Status": "Enabled",
    "Expiration": {"Days": 1},
}

# Export files are served via a 15-min presigned URL and never deleted
# otherwise; this rule reaps them. One day comfortably outlives the TTL.
_EXPORT_LIFECYCLE_RULE = {
    "ID": "expire-temp-exports",
    "Filter": {"Prefix": EXPORT_PREFIX},
    "Status": "Enabled",
    "Expiration": {"Days": 1},
}


class Command(BaseCommand):
    help = (
        "Set (or display) the bucket CORS rules allowing direct browser uploads "
        "via presigned POST."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--origin",
            action="append",
            dest="origins",
            default=[],
            help=(
                "Allowed browser origin (scheme + host + port), e.g. "
                "http://localhost:8000. Repeat for several origins. Defaults to "
                "https://<host> for each ALLOWED_HOSTS entry when omitted."
            ),
        )
        parser.add_argument(
            "--show",
            action="store_true",
            help="Only print the bucket's current CORS configuration.",
        )

    def handle(self, *args, **options):
        bucket = settings.AWS_STORAGE_BUCKET_NAME
        if not bucket:
            raise CommandError("AWS_STORAGE_BUCKET_NAME is not configured.")

        s3 = get_s3_client()

        if options["show"]:
            self._show(s3, bucket)
            return

        origins = options["origins"] or [
            f"https://{host}" for host in settings.ALLOWED_HOSTS if host
        ]
        if not origins:
            raise CommandError(
                "No --origin given and ALLOWED_HOSTS is empty; provide at least "
                "one --origin (e.g. --origin http://localhost:8000)."
            )

        s3.put_bucket_cors(
            Bucket=bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedMethods": ["POST"],
                        "AllowedOrigins": origins,
                        "AllowedHeaders": ["*"],
                        "ExposeHeaders": ["ETag", "Location"],
                        "MaxAgeSeconds": 3600,
                    }
                ]
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"CORS rule set on bucket {bucket!r} for origins: {', '.join(origins)}"
            )
        )

        s3.put_bucket_lifecycle_configuration(
            Bucket=bucket,
            LifecycleConfiguration={
                "Rules": [_IMPORT_LIFECYCLE_RULE, _EXPORT_LIFECYCLE_RULE]
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Lifecycle rules set on bucket {bucket!r}: objects under "
                f"{DocumentImportJob.TEMP_S3_PREFIX!r} and {EXPORT_PREFIX!r} "
                "expire after 1 day."
            )
        )

    def _show(self, s3, bucket):
        from botocore.exceptions import ClientError

        try:
            config = s3.get_bucket_cors(Bucket=bucket)
        except ClientError as error:
            if error.response["Error"]["Code"] == "NoSuchCORSConfiguration":
                self.stdout.write(f"Bucket {bucket!r} has no CORS configuration.")
            else:
                raise
        else:
            for rule in config.get("CORSRules", []):
                self.stdout.write(str(rule))

        try:
            lifecycle = s3.get_bucket_lifecycle_configuration(Bucket=bucket)
        except ClientError as error:
            if error.response["Error"]["Code"] == "NoSuchLifecycleConfiguration":
                self.stdout.write(f"Bucket {bucket!r} has no lifecycle configuration.")
                return
            raise
        for rule in lifecycle.get("Rules", []):
            self.stdout.write(str(rule))
