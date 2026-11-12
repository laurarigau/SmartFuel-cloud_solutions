import importlib.util
import json
from pathlib import Path

# Load the ingestion handler directly from its file.
# This avoids conflicts with other Lambda files named handler.py.
handler_path = Path(__file__).with_name("handler.py")

spec = importlib.util.spec_from_file_location(
    "ingest_handler",
    handler_path
)

handler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler)


def test_lambda_handler_uploads_raw_data(monkeypatch):
    monkeypatch.setenv("LAKE_BUCKET", "test-smartfuel-bucket")

    sample_data = {
        "Fecha": "12/11/2026 09:00:00",
        "ListaEESSPrecio": [
            {"IDEESS": "1234", "Precio Gasolina 95 E5": "1,450"},
            {"IDEESS": "5678", "Precio Gasolina 95 E5": "1,520"}
        ]
    }

    original_json = json.dumps(sample_data).encode("utf-8")

    class FakeResponse:
        content = original_json

        def raise_for_status(self):
            pass

        def json(self):
            return sample_data

    def fake_get(url, headers, timeout):
        return FakeResponse()

    monkeypatch.setattr(handler.requests, "get", fake_get)

    uploaded_objects = []

    def fake_put_object(**kwargs):
        uploaded_objects.append(kwargs)

    monkeypatch.setattr(handler.s3, "put_object", fake_put_object)

    response = handler.lambda_handler({}, None)

    assert response["statusCode"] == 200

    body = json.loads(response["body"])

    assert body["message"] == "Fuel data ingested successfully"
    assert body["bucket"] == "test-smartfuel-bucket"
    assert body["key"] == "raw/2026/11/12/0900.json"
    assert body["station_count"] == 2

    assert len(uploaded_objects) == 1

    uploaded = uploaded_objects[0]

    assert uploaded["Bucket"] == "test-smartfuel-bucket"
    assert uploaded["Key"] == "raw/2026/11/12/0900.json"
    assert uploaded["Body"] == original_json
    assert uploaded["ContentType"] == "application/json"
