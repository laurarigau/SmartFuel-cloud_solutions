"""Shared test helpers: in-memory fakes for S3, SNS and DynamoDB (no AWS, no moto)."""
import importlib.util
import io
import json
import pathlib

import pytest

LAMBDAS = pathlib.Path(__file__).parent
FIXTURES = LAMBDAS.parent.parent / "fixtures"


def load_handler(name):
    """Import src/lambdas/<name>/handler.py under a unique module name."""
    path = LAMBDAS / name / "handler.py"
    spec = importlib.util.spec_from_file_location(f"{name.replace('-', '_')}_handler", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_json(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeS3:
    def __init__(self):
        self.objects = {}  # (bucket, key) -> bytes

    def put_object(self, Bucket, Key, Body, **_):
        self.objects[(Bucket, Key)] = Body if isinstance(Body, bytes) else Body.encode()

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise KeyError(f"NoSuchKey: {Key}")
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def copy_object(self, Bucket, Key, CopySource):
        self.objects[(Bucket, Key)] = self.objects[(CopySource["Bucket"], CopySource["Key"])]

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def list_objects_v2(self, Bucket, Prefix, **_):
        keys = sorted(k for (b, k) in self.objects if b == Bucket and k.startswith(Prefix))
        return {"Contents": [{"Key": k} for k in keys], "IsTruncated": False}

    def keys(self, prefix=""):
        return sorted(k for (_, k) in self.objects if k.startswith(prefix))


class FakeSNS:
    def __init__(self):
        self.messages = []

    def publish(self, **kwargs):
        self.messages.append(kwargs)


class FakeTable:
    def __init__(self, keys):
        self.key_names = keys
        self.items = {}

    def batch_writer(self, **_):
        table = self

        class Writer:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def put_item(self, Item):
                table.items[tuple(Item[k] for k in table.key_names)] = Item

        return Writer()


class FakeDynamo:
    KEYS = {
        "smartfuel-stations": ["station_id"],
        "smartfuel-latest-prices": ["station_id", "fuel_type"],
        "smartfuel-predictions": ["station_fuel", "date"],
    }

    def __init__(self):
        self.tables = {}

    def Table(self, name):
        if name not in self.tables:
            self.tables[name] = FakeTable(self.KEYS[name])
        return self.tables[name]


@pytest.fixture
def fake_s3():
    return FakeS3()


@pytest.fixture
def fake_sns():
    return FakeSNS()


@pytest.fixture
def fake_dynamo():
    return FakeDynamo()


@pytest.fixture
def env(monkeypatch):
    values = {
        "LAKE_BUCKET": "lake",
        "MIN_STATIONS": "10",
        "ADMIN_TOPIC_ARN": "arn:aws:sns:us-east-1:000000000000:smartfuel-admin-alerts",
        "STATIONS_TABLE": "smartfuel-stations",
        "LATEST_PRICES_TABLE": "smartfuel-latest-prices",
        "PREDICTIONS_TABLE": "smartfuel-predictions",
    }
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    return values


@pytest.fixture
def load():
    """load("validate") -> the handler module."""
    return load_handler


@pytest.fixture
def raw_sample():
    return fixture_json("raw_sample.json")


@pytest.fixture
def raw_invalid():
    return fixture_json("raw_invalid.json")
