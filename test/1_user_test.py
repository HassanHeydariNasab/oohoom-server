import pytest
from falcon import testing

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
        assert resp.json == {"is_user_exists": False}

    def test_post_user(self, oohoom):
        code = r_code.r_mobile_code.get(MOBILE)
        assert code
        resp = oohoom.simulate_post(
            "/v1/users",
            json={
                "code": code.decode(),
                "mobile": MOBILE,
                "name": "an_employee",
                "role": "employee",
                "skills": [],
            },
        )
        assert "token" in resp.json
        g["token"] = resp.json["token"]

    def test_post_code_again(self, oohoom):
        resp = oohoom.simulate_post("/v1/code", json={"mobile": MOBILE})
        assert resp.json == {"is_user_exists": True}

    def test_post_token(self, oohoom):
        code = r_code.r_mobile_code.get(MOBILE)
        assert code
        resp = oohoom.simulate_post(
            "/v1/token", json={"code": code.decode(), "mobile": MOBILE},
        )
        assert "token" in resp.json
        g["token"] = resp.json["token"]

    def test_get_user(self, oohoom):
        resp = oohoom.simulate_get(
            "/v1/users/me", headers={"Authorization": g["token"]}
        )
        assert "_id" in resp.json

    def test_get_employees(self, oohoom):
        resp = oohoom.simulate_get(
            "/v1/users?role=employee", headers={"Authorization": g["token"]}
        )
        assert type(resp.json) == list
        assert len(resp.json) == 1

    def test_get_user_by_name(self, oohoom):
        resp = oohoom.simulate_get(
            "/v1/users/An_Employee", headers={"Authorization": g["token"]}
        )
        assert type(resp.json) == dict
        assert resp.json["name"] == "an_employee"

    def test_get_user_by_invalid_name(self, oohoom):
        resp = oohoom.simulate_get(
            "/v1/users/An_Employee-", headers={"Authorization": g["token"]}
        )
        assert resp.status_code == 404
