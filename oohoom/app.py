import string
from datetime import datetime
from random import SystemRandom

import falcon
from bson.json_util import dumps, loads
from kavenegar import KavenegarAPI
from pymongo import MongoClient, ASCENDING, DESCENDING

from . import r_code
from .constants import LIMIT
from .converters import UserNameConverter
from .hooks import auth, validate_req
from .jwt_user_id import user_to_token
from .local_config import KAVENEGAR_APIKEY, IS_DEBUGGING
from .utils import normalized_mobile
from .middlewares import cors

client = MongoClient()
db = client.test_oohoom

is_debugging = IS_DEBUGGING  # manually enable testing situation (db,...)
global_is_testing = is_debugging


class UserResource(object):
    @falcon.before(
        validate_req,
        {
            "role": {
                "type": "string",
                "regex": "^(employer|employee|all)$",
                "default": "all",
            },
            "state": {
                "type": "string",
                "regex": "^(idle|busy|all)$",
                "default": "all",
            },
            "skip": {"type": "integer", "coerce": int, "min": 0, "default": 0},
            "limit": {"type": "integer", "coerce": int, "min": 1, "default": LIMIT},
        },
        require_all=False,
        produce_filter=True,
    )
    def on_get(self, req, resp):
        users = list(
            db.users.find(
                req.context.filter,
                skip=req.context.params.get("skip"),
                limit=req.context.params.get("limit"),
                projection={"_id": 1, "name": 1, "role": 1, "state": 1, "skills": 1},
            )
        )
        # TODO: sort employees by rank
        resp.media = users

    def on_get_name(self, req, resp, name):
        user = db.users.find_one(
            {"name": name},
            projection={"_id": 1, "name": 1, "role": 1, "state": 1, "skills": 1},
        )
        if user is None:
            raise falcon.errors.HTTPNotFound(description="user not found")
        resp.media = user

    @falcon.before(auth)
    def on_get_me(self, req, resp):
        user = db.users.find_one({"_id": req.context.user_id})
        # a rare case
        if user is None:
            raise falcon.errors.HTTPNotFound(description="user not found")
        resp.media = user

    # registration
    @falcon.before(
        validate_req,
        {
            "code": {"type": "string"},
            "mobile": {"type": "string", "minlength": 5, "maxlength": 30},
            "name": {
                "type": "string",
                "maxlength": 36,
                "minlength": 1,
                "regex": "^(?!(me)$)[a-z0-9_]+$",
            },
            "role": {"type": "string", "allowed": ["employer", "employee"]},
            "skills": {
                "type": "list",
                "schema": {"type": "string", "minlength": 1, "maxlength": 36},
                "maxlength": 30,
            },
        },
    )
    def on_post(self, req, resp):
        req.media["mobile"] = normalized_mobile(req.media.get("mobile"))
        if not r_code.is_valid(req.media.get("mobile"), req.media.get("code")):
            raise falcon.errors.HTTPBadRequest(description={"code": "code is invalid"})
        if (
            db.users.find_one(
                {"mobile": req.media.get("mobile")}, projection={"mobile": 1}
            )
            is not None
        ):
            raise falcon.errors.HTTPConflict(
                title="mobile",
                description={"mobile": "A user with this mobile number already exists"},
            )
        if (
            db.users.find_one({"name": req.media.get("name")}, projection={"name": 1})
            is not None
        ):
            raise falcon.errors.HTTPConflict(
                title="name",
                description={"name": "A user with this name already exists"},
            )
        result = db.users.insert_one(
            {
                "mobile": req.media.get("mobile"),
                "name": req.media.get("name"),
                "role": req.media.get("role"),
                "state": "idle",
                "skills": req.media.get("skills"),
            }
        )
        token = user_to_token(str(result.inserted_id))
        resp.media = {"token": token}
        resp.status = falcon.HTTP_CREATED


class CodeResource(object):
    # send verification sms
    @falcon.before(
        validate_req, {"mobile": {"type": "string", "minlength": 5, "maxlength": 30}}
    )
    def on_post(self, req, resp):
        req.media["mobile"] = normalized_mobile(req.media.get("mobile"))
        is_user_exists = False
        if (
            db.users.find_one(
                {"mobile": req.media.get("mobile")}, projection={"mobile": 1}
            )
            is not None
        ):
            is_user_exists = True
        code = "".join(SystemRandom().choice(string.digits) for digit in range(5))
        try:
            api = KavenegarAPI(KAVENEGAR_APIKEY)
            params = {
                "receptor": req.media.get("mobile"),
                "message": "oohoom: " + code,
            }
            if not global_is_testing:
                response = api.sms_send(params)
                print(response)
        except Exception as e:
            print("Error [kavenegar]: ", e)
            raise falcon.HTTPInternalServerError()
        else:
            r_code.store(req.media.get("mobile"), code)
            resp.media = {"is_user_exists": is_user_exists}
            resp.status = falcon.HTTP_CREATED


class TokenResource(object):
    # login
    @falcon.before(
        validate_req,
        {
            "mobile": {"type": "string", "minlength": 5, "maxlength": 30},
            "code": {"type": "string"},
        },
    )
    def on_post(self, req, resp):
        req.media["mobile"] = normalized_mobile(req.media.get("mobile"))
        if not r_code.is_valid(req.media.get("mobile"), req.media.get("code")):
            raise falcon.errors.HTTPBadRequest(description={"code": "code is invalid"})
        user = db.users.find_one({"mobile": req.media.get("mobile")})
        if user is None:
            raise falcon.errors.HTTPBadRequest(description={"code": "code is invalid"})
        token = user_to_token(str(user["_id"]))
        resp.media = {"token": token}


class ProjectResource(object):
    @falcon.before(auth)
    @falcon.before(
        validate_req,
        {
            "title": {"type": "string", "minlength": 1, "maxlength": 88},
            "description": {"type": "string", "minlength": 0, "maxlength": 500},
            "skills": {
                "type": "list",
                "schema": {"type": "string", "minlength": 1, "maxlength": 36},
                "maxlength": 30,
            },
        },
    )
    def on_post(self, req, resp):
        employer = db.users.find_one(
            {"_id": req.context.user_id, "role": "employer"},
            projection={"_id": 1, "name": 1},
        )
        if employer is None:
            raise falcon.errors.HTTPForbidden(
                description="You must be an employer to post a project."
            )
        project = db.projects.find_one({"title": req.media.get("title")})
        if project is not None:
            raise falcon.errors.HTTPConflict(
                description={"title": "This title already exists."}
            )
        result = db.projects.insert_one(
            {
                "title": req.media.get("title"),
                "description": req.media.get("description"),
                "employer": {"_id": req.context.user_id, "name": employer.get("name")},
                "state": "new",
                "skills": req.media.get("skills"),
                "creation_datetime": datetime.utcnow(),
            }
        )
        resp.media = {"_id": result.inserted_id}

    @falcon.before(
        validate_req,
        {
            "state": {
                "type": "string",
                "regex": "^(new|assigned|done|closed|all)$",
                "default": "all",
            },
            "skip": {"type": "integer", "coerce": int, "min": 0, "default": 0},
            "limit": {"type": "integer", "coerce": int, "min": 1, "default": LIMIT},
        },
        require_all=False,
        produce_filter=True,
    )
    def on_get(self, req, resp):
        projects = list(
            db.projects.find(
                req.context.filter,
                skip=req.context.params.get("skip"),
                limit=req.context.params.get("limit"),
            ).sort("_id", DESCENDING)
        )
        # TODO: sort projects according to skills
        resp.media = projects

    def on_get_title(self, req, resp, title):
        project = db.projects.find_one({"title": title})
        if project is None:
            raise falcon.errors.HTTPNotFound(description="project not found")
        resp.media = project

    @falcon.before(
        validate_req,
        {
            "action": {
                "type": "string",
                "regex": "^(assign|update)$",
                "required": True,
            },
            "_id": {"type": "objectid", "required": True},
            "update": {
                "type": "dict",
                "schema": {
                    "description": {"type": "string", "minlength": 0, "maxlength": 500},
                    "skills": {
                        "type": "list",
                        "schema": {"type": "string", "minlength": 1, "maxlength": 36},
                        "maxlength": 30,
                    },
                },
                "dependencies": {"action": "update"},
            },
        },
        require_all=False,
    )
    @falcon.before(auth)
    def on_patch(self, req, resp):
        # employee performs this action
        if req.context.params.get("action") == "assign":
            employee = db.users.find_one(
                {"_id": req.context.user_id, "role": "employee"},
                projection={"_id": 1, "name": 1},
            )
            if employee is None:
                raise falcon.errors.HTTPUnauthorized(
                    description="You must be an employee to accept project."
                )
            result = db.projects.update_one(
                {
                    "_id": req.context.params.get("_id"),
                    "employee": {"$exists": False},
                    "state": "new",
                },
                {"$set": {"employee": employee}},
            )
            if result.matched_count == 1:
                resp.media = result.raw_result
            else:
                raise falcon.errors.HTTPNotFound(description="no new project found")
        # employer performs this action
        elif (
            req.context.params.get("action") == "update"
            and req.context.params.get("update") is not None
        ):
            result = db.projects.update_one(
                {"_id": req.context.params.get("_id")},
                {"$set": req.context.params.get("update")},
            )
            if result.matched_count == 1:
                resp.media = result.raw_result
            else:
                raise falcon.errors.HTTPNotFound(description="project not found")


class TestResource(object):
    def on_get(self, req, resp):
        resp.media = {"ok": True}


def create_app(is_testing=False):
    app = falcon.App(middleware=[cors()])
    global db, global_is_testing
    # create_app was called within a test
    if is_testing:
        print("test db")
        client = MongoClient()
        db = client.test_oohoom
        # in order to use inside of Resource
        global_is_testing = True
    else:
        print("production db")
        client = MongoClient()
        db = client.oohoom

    app.router_options.converters["user_name"] = UserNameConverter

    json_handler = falcon.media.JSONHandler(dumps=dumps, loads=loads,)
    extra_handlers = {
        "application/json": json_handler,
    }
    app.req_options.media_handlers.update(extra_handlers)
    app.resp_options.media_handlers.update(extra_handlers)

    test = TestResource()
    user = UserResource()
    code = CodeResource()
    token = TokenResource()
    project = ProjectResource()

    app.add_route("/v1/test", test)
    app.add_route("/v1/users", user)
    app.add_route("/v1/users/me", user, suffix="me")
    app.add_route("/v1/users/{name:user_name}", user, suffix="name")
    app.add_route("/v1/code", code)
    app.add_route("/v1/token", token)
    app.add_route("/v1/projects", project)
    app.add_route("/v1/projects/{title}", project, suffix="title")
    return app


app = create_app(is_testing=is_debugging)
