import io
import json

import pytest

EVENT = {"detail": {"bucket": {"name": "lake"}, "object": {"key": "raw/2026/11/04/1325.json"}}}


class FakeLambda:
    """Answers each step with a canned result; can fail a step N times."""

    def __init__(self, results, fail=None):
        self.results = results
        self.fail = dict(fail or {})  # step -> number of times it fails
        self.calls = []

    def invoke(self, FunctionName, InvocationType, Payload):
        step = FunctionName.replace("fn-", "")
        self.calls.append(step)
        if self.fail.get(step, 0) > 0:
            self.fail[step] -= 1
            return {"FunctionError": "Unhandled", "Payload": io.BytesIO(b'{"errorMessage": "boom"}')}
        return {"Payload": io.BytesIO(json.dumps(self.results[step]).encode())}


RESULTS = {
    "validate": {"bucket": "lake", "key": "raw/2026/11/04/1325.json", "valid": True, "reasons": [], "stations": 11465},
    "clean": {"bucket": "lake", "clean_key": "clean/date=2026-11-04/1325.parquet",
              "changes_key": "changes/date=2026-11-04/1325.jsonl.gz", "rows": 34531, "changes": 120},
    "save-changes": {"prices_written": 120, "stations_written": 0},
    "predict": {"predictions_written": 34531, "model_version": "stub"},
}


@pytest.fixture
def h(load, fake_sns, monkeypatch):
    for step in ("validate", "clean", "save_changes", "predict"):
        monkeypatch.setenv(f"FN_{step.upper()}", f"fn-{step.replace('_', '-')}")
    monkeypatch.setenv("BACKOFF_SECONDS", "0")
    monkeypatch.setenv("ADMIN_TOPIC_ARN", "arn:aws:sns:us-east-1:000000000000:smartfuel-admin-alerts")
    module = load("process")
    module._sns = fake_sns
    return module


def test_happy_path_runs_all_steps(h):
    h._lambda = fake = FakeLambda(RESULTS)
    out = h.lambda_handler(EVENT, None)

    assert out["status"] == "processed"
    assert fake.calls[:2] == ["validate", "clean"]
    assert sorted(fake.calls[2:]) == ["predict", "save-changes"]
    assert out["steps"]["clean"] == {"rows": 34531, "changes": 120}
    assert out["steps"]["predict"]["model_version"] == "stub"


def test_invalid_file_stops_after_validate(h, fake_sns):
    invalid = {**RESULTS, "validate": {**RESULTS["validate"], "valid": False, "reasons": ["missing list"]}}
    h._lambda = fake = FakeLambda(invalid)
    out = h.lambda_handler(EVENT, None)

    assert out["status"] == "quarantined"
    assert fake.calls == ["validate"]
    assert fake_sns.messages == []  # validate already alerted


def test_retry_then_success(h, fake_sns):
    h._lambda = fake = FakeLambda(RESULTS, fail={"clean": 2})
    out = h.lambda_handler(EVENT, None)

    assert out["status"] == "processed"
    assert fake.calls.count("clean") == 3
    assert fake_sns.messages == []


def test_final_failure_alerts_and_raises(h, fake_sns):
    h._lambda = fake = FakeLambda(RESULTS, fail={"predict": 5})
    with pytest.raises(h.StepFailed):
        h.lambda_handler(EVENT, None)

    assert fake.calls.count("predict") == 3
    assert len(fake_sns.messages) == 1
    assert "Step: predict" in fake_sns.messages[0]["Message"]


def test_no_sns_topic_still_raises(h, fake_sns, monkeypatch, capsys):
    monkeypatch.delenv("ADMIN_TOPIC_ARN")
    h._lambda = FakeLambda(RESULTS, fail={"validate": 5})
    with pytest.raises(h.StepFailed):
        h.lambda_handler(EVENT, None)
    assert fake_sns.messages == []
    assert "ERROR SmartFuel: processing failed" in capsys.readouterr().out
