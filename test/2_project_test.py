import pytest
from falcon import testing
from pymongo import MongoClient

from ..oohoom import app, r_code


MOBILE = "00989352904135"


@pytest.fixture(scope="function")
def oohoom():
    return testing.TestClient(app.create_app(is_testing=True))


g = {}


def test_test(oohoom):
    doc = {"ok": True}
    result = oohoom.simulate_get("/v1/test")
    assert result.json == doc


@pytest.mark.incremental
class TestProject:
    def test_post_code(self, oohoom):
        resp = oohoom.simulate_post("/v1/code", json={"mobile": MOBILE})
        assert resp.json == {"is_user_exists": False}

    def test_post_user(self, oohoom):
        code = r_code.r_mobile_code.get(MOBILE)
        assert code
        resp = oohoom.simulate_post(
            "/v1/user",
            json={
                "code": code.decode(),
                "mobile": MOBILE,
                "name": "an_employer",
                "role": "employer",
                "skills": [],
            },
        )
        assert "token" in resp.json
        g["token"] = resp.json["token"]

    def test_post_project(self, oohoom):
        resp = oohoom.simulate_post(
            "/v1/project",
            json={
                "title": "A project",
                "description": "This is a project",
                "skills": ["test", "testing", "tested"],
            },
            headers={"Authorization": g["token"]},
        )
        assert "_id" in resp.json
