
import json
import handler


def test_lambda_handler_uploads_raw_data(monkeypatch):

    # 1. Simulate the S3 bucket environment variable
    monkeypatch.setenv("LAKE_BUCKET", "test-smartfuel-bucket")

    # 2. Create a sample API response
    sample_data = {
        "Fecha": "12/11/2026 09:00:00",
        "ListaEESSPrecio": [
            {"IDEESS": "1234", "Precio Gasolina 95 E5": "1,450"},
            {"IDEESS": "5678", "Precio Gasolina 95 E5": "1,520"}
        ]
    }

    original_json = json.dumps(sample_data).encode("utf-8")

    # 3. Simulate the API response
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return original_json

    def fake_urlopen(request, timeout):
        return FakeResponse()

    monkeypatch.setattr(
        handler.urllib.request,
        "urlopen",
        fake_urlopen
    )

    # 4. Capture the S3 upload instead of actually uploading
    uploaded_objects = []

    def fake_put_object(**kwargs):
        uploaded_objects.append(kwargs)

    monkeypatch.setattr(
        handler.s3,
        "put_object",
        fake_put_object
    )

    # 5. Execute the Lambda
    result = handler.lambda_handler({}, None)

    # 6. Check the result
    assert result["statusCode"] == 200

    assert len(uploaded_objects) == 1

    assert uploaded_objects[0]["Bucket"] == "test-smartfuel-bucket"

    assert uploaded_objects[0]["Key"] == "raw/2026/11/12/0900.json"

    assert uploaded_objects[0]["Body"] == original_json

    assert uploaded_objects[0]["ContentType"] == "application/json"
