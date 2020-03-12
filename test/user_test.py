from falcon import testing
import pytest

# import oohoom
from ..oohoom import app


@pytest.fixture()
def client():
    return testing.TestClient(app.create_app())


def test_test(client):
    doc = {"ok": True}
    result = client.simulate_get("/v1/test")
    assert result.json == doc

