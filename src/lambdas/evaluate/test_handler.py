import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def module():
    path = Path(__file__).with_name("handler.py")
    spec = importlib.util.spec_from_file_location("phase_c_evaluate_handler", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CANDIDATE = {"metrics": {"macro_f1": 0.4199, "baseline_macro_f1": 0.3084}}


def test_evaluate_candidate(module):
    result = module.evaluate(CANDIDATE)
    assert result["status"] == "eligible"
    assert result["production_promoted"] is False  # evaluate() only decides


def test_not_eligible_when_not_better_than_production(module):
    result = module.evaluate(CANDIDATE, {"metrics": {"macro_f1": 0.45}})
    assert result["status"] == "not_eligible"
    assert result["reasons"] == ["below_production"]


def test_not_eligible_below_baseline(module):
    result = module.evaluate({"metrics": {"macro_f1": 0.30, "baseline_macro_f1": 0.31}})
    assert result["reasons"] == ["below_baseline"]


class FakeS3:
    def __init__(self):
        self.copies = []

    def copy_object(self, Bucket, Key, CopySource):
        self.copies.append((CopySource["Key"], Key))


def test_promote_archives_then_copies_metadata_last(module):
    s3 = FakeS3()
    now = datetime(2026, 11, 23, 2, 0, tzinfo=timezone.utc)
    archived = module.promote(s3, "lake", "models/candidates/run1/", True, now)
    assert archived == "models/archive/20261123T020000Z/"
    assert s3.copies == [
        ("models/production/model.joblib", "models/archive/20261123T020000Z/model.joblib"),
        ("models/production/metadata.json", "models/archive/20261123T020000Z/metadata.json"),
        ("models/candidates/run1/model.joblib", "models/production/model.joblib"),
        ("models/candidates/run1/metadata.json", "models/production/metadata.json"),
    ]


def test_promote_first_model_without_archive(module):
    s3 = FakeS3()
    assert module.promote(s3, "lake", "models/candidates/run1/", False, datetime.now(timezone.utc)) is None
    assert len(s3.copies) == 2


def test_notify_admins(module, monkeypatch):
    sent = []

    class FakeSNS:
        def publish(self, **kwargs):
            sent.append(kwargs)

    import boto3
    monkeypatch.setattr(boto3, "client", lambda name: FakeSNS())
    result = {**module.evaluate(CANDIDATE, {"metrics": {"macro_f1": 0.5}}), "candidate_prefix": "models/candidates/r/"}

    monkeypatch.delenv("ADMIN_TOPIC_ARN", raising=False)
    assert module.notify_admins(result) is False and sent == []

    monkeypatch.setenv("ADMIN_TOPIC_ARN", "arn:aws:sns:eu-north-1:1:smartfuel-admin-alerts")
    assert module.notify_admins(result) is True
    assert sent[0]["Subject"] == "SmartFuel: new ML model not promoted"
    assert "below_production" in sent[0]["Message"]
