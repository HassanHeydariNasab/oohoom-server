import pytest
from falcon import testing

from ..oohoom import app, r_code


EMPLOYER_MOBILE = "00989352904135"
EMPLOYEE_MOBILE = "00989389742591"


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
        resp = oohoom.simulate_post("/v1/code", json={"mobile": EMPLOYER_MOBILE})
        assert resp.json == {"is_user_exists": False}

    def test_post_user(self, oohoom):
        code = r_code.r_mobile_code.get(EMPLOYER_MOBILE)
        assert code
        resp = oohoom.simulate_post(
            "/v1/users",
            json={
                "code": code.decode(),
                "mobile": EMPLOYER_MOBILE,
                "name": "an_employer",
                "role": "employer",
                "skills": [],
            },
        )
        assert "token" in resp.json
        g["token"] = resp.json["token"]
        print("employer token:", g["token"])

    def test_post_project(self, oohoom):
        resp = oohoom.simulate_post(
            "/v1/projects",
            json={
                "title": "A project",
                "description": "This is a project.",
                "skills": ["test", "testing", "tested"],
            },
            headers={"Authorization": g["token"]},
        )
        assert "_id" in resp.json
        g['project_id'] = resp.json["_id"]

    def test_get_projects(self, oohoom):
        resp = oohoom.simulate_get("/v1/projects")
        assert type(resp.json) == list
        assert len(resp.json) == 1

   # def test_get_project_title(self, oohoom):
   #     resp = oohoom.simulate_get("/v1/projects/A project")
   #     assert type(resp.json) == dict
   #     assert "_id" in resp.json
   #     g["project_id"] = resp.json.get("_id")

    # switch to employee
    def test_post_code_again(self, oohoom):
        resp = oohoom.simulate_post("/v1/code", json={"mobile": EMPLOYEE_MOBILE})
        assert resp.json == {"is_user_exists": True}

    def test_post_token(self, oohoom):
        code = r_code.r_mobile_code.get(EMPLOYEE_MOBILE)
        assert code
        resp = oohoom.simulate_post(
            "/v1/token", json={"code": code.decode(), "mobile": EMPLOYEE_MOBILE},
        )
        assert "token" in resp.json
        g["token"] = resp.json["token"]

    def test_patch_project_assign(self, oohoom):
        resp = oohoom.simulate_patch(
            "/v1/projects",
            json={"_id": g["project_id"], "action": "assign"},
            headers={"Authorization": g["token"]},
        )
        assert resp.status_code == 200

    def test_patch_project_update(self, oohoom):
        resp = oohoom.simulate_patch(
            "/v1/projects",
            json={
                "_id": g["project_id"],
                "action": "update",
                "update": {"description": "This is an updated project."},
            },
            headers={"Authorization": g["token"]},
        )
        assert resp.status_code == 200
        resp = oohoom.simulate_get(
            "/v1/projects/"+g['project_id']['$oid'], headers={"Authorization": g["token"]},
        )
        assert "This is an updated project." == resp.json.get("description")
