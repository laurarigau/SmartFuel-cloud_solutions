
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def test_train_lambda(monkeypatch):
    path = Path(__file__).with_name("handler.py")
    spec = importlib.util.spec_from_file_location(
        "phase_c_train_handler", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def fake_train_model(**kwargs):
        assert kwargs["s3_bucket"] == "test-bucket"
        return {
            "candidate_prefix": "models/candidates/test/"
        }

    monkeypatch.setitem(
        sys.modules,
        "train_model",
        SimpleNamespace(train_model=fake_train_model)
    )

    monkeypatch.setenv("LAKE_BUCKET", "test-bucket")
    monkeypatch.delenv("EVALUATE_FUNCTION_NAME", raising=False)

    result = module.lambda_handler({}, None)

    assert result["candidate_prefix"] == "models/candidates/test/"
    assert result["evaluation_requested"] is False
