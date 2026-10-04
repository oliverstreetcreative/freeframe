"""OSC 0012: the API's extra CORS origins also get storage-bucket CORS rules.

A second site embedding the player (the OSC client portal on staging) fetches presigned HLS
segments straight from the bucket, so the bucket must allow that origin too. Before this, the
startup CORS write named FRONTEND_URL + localhost only and overwrote anything else.
"""
from apps.api.config import settings
from apps.api.services import s3_service
from apps.api.services.s3_service import ensure_bucket_exists


class _FakeS3:
    def __init__(self):
        self.cors_config = None

    def head_bucket(self, **kwargs):
        return {}

    def put_bucket_cors(self, Bucket, CORSConfiguration):
        self.cors_config = CORSConfiguration

    def put_bucket_policy(self, **kwargs):
        return {}


def _origins(monkeypatch, extra):
    monkeypatch.setattr(settings, "s3_storage", "minio")
    monkeypatch.setattr(settings, "frontend_url", "https://review.example.com")
    monkeypatch.setattr(settings, "cors_allow_origins", extra)
    fake = _FakeS3()
    monkeypatch.setattr(s3_service, "_build_s3_client", lambda config=None: fake)
    ensure_bucket_exists()
    return [r["AllowedOrigins"] for r in fake.cors_config["CORSRules"]]


def test_extra_api_origins_get_one_bucket_rule_each(monkeypatch):
    got = _origins(monkeypatch, "https://portal-staging.example.com, https://edge.example.com/")
    assert got == [["https://review.example.com"], ["https://portal-staging.example.com"],
                   ["https://edge.example.com"], ["http://localhost:3000"]]


def test_a_wildcard_is_never_copied_onto_the_bucket(monkeypatch):
    got = _origins(monkeypatch, "*")
    assert got == [["https://review.example.com"], ["http://localhost:3000"]]


def test_no_extras_is_upstream_behaviour(monkeypatch):
    assert _origins(monkeypatch, "") == [["https://review.example.com"], ["http://localhost:3000"]]
