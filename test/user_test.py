from falcon import testing
from pymongo import MongoClient
import pytest
from ..oohoom import app, r_code
from ..oohoom.init import mongodb


MOBILE = "00989389742591"


@pytest.fixture(scope="function")
def oohoom():
    return testing.TestClient(app.create_app(is_testing=True))


g = {}


def test_test(oohoom):
    doc = {"ok": True}
    result = oohoom.simulate_get("/v1/test")
    assert result.json == doc


@pytest.mark.incremental
class TestRegistration:
    def test_init_mongodb(self):
        assert mongodb.init(is_testing=True)

    def test_post_code(self, oohoom):
        resp = oohoom.simulate_post("/v1/code", json={"mobile": MOBILE})
        assert "is_user_exists" in resp.json

    def test_post_user(self, oohoom):
        code = r_code.r_mobile_code.get(MOBILE)
        assert code
        resp = oohoom.simulate_post(
            "/v1/user",
            json={
                "code": code.decode(),
                "mobile": MOBILE,
                "name": "Hassan",
                "role": "employee",
                "skills": [],
            },
        )
        assert "token" in resp.json.keys()
        g["token"] = resp.json["token"]

    def test_get_user(self, oohoom):
        resp = oohoom.simulate_get("/v1/user", headers={"Authorization": g["token"]})
        assert "_id" in resp.json
