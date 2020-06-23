import string
import os
import io
from mimetypes import guess_type
from random import SystemRandom
from datetime import datetime
from random import SystemRandom

import falcon
from falcon.request import Request
from falcon.response import Response 
from bson.json_util import dumps, loads
from bson import ObjectId
from kavenegar import KavenegarAPI
from pymongo import MongoClient, ASCENDING, DESCENDING

from . import r_code
from .constants import LIMIT
from .converters import UserNameConverter, ObjectIdConverter
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
                "token": code,
                "template": "code"
            }
            if not global_is_testing:
                response = api.verify_lookup(params)
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
                "employee": None,
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

    def on_get__id(self, req: Request, resp: Response, _id: ObjectId):
        project = db.projects.find_one({"_id": _id})
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
                    "employee": None,
                    "state": "new",
                },
                {"$set": {"employee": employee, "state": "assigned"}},
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


class FileResource(object):
    @falcon.before(auth)
    def on_post(self, req: Request, resp: Response):
        if req.content_type.split(';')[0] == 'multipart/form-data':
            file_ = {'creation_datetime': datetime.utcnow()}
            for part in req.media:
                if part.name == 'file':
                    file_['title'] = part.filename
                    temp_filename = ''.join(SystemRandom().choice(string.digits+string.ascii_lowercase) for digit in range(32))
                    with io.open(os.path.join('uploads', 'files', temp_filename), 'wb') as dest:
                        part.stream.pipe(dest) 
                elif part.name == 'project_id':
                    file_['project_id'] = ObjectId(part.text)
                elif part.name == 'kind':
                    file_['kind'] = part.text
                    if file_['kind'] not in ['input', 'output']:
                        os.remove(os.path.join('uploads', 'files', temp_filename)) 
                        raise falcon.errors.HTTPBadRequest(title='`kind` should be `input|output`')
            role = {'input': 'employer._id', 'output': 'employee._id'}
            project = db.projects.find_one({'_id': file_['project_id'], role[file_['kind']]: req.context.user_id})
            if project is None:
                os.remove(os.path.join('uploads', 'files', temp_filename)) 
                raise falcon.errors.HTTPForbidden(title='no such project found for you')
            result = db.files.insert_one(file_)
            os.rename(os.path.join('uploads', 'files', temp_filename), os.path.join('uploads', 'files', str(result.inserted_id)))
            resp.status = falcon.HTTP_201
            resp.media = {'_id': result.inserted_id}
        else:
            raise falcon.errors.HTTPUnsupportedMediaType(title='multipart/form-data required')

    @falcon.before(auth, optional=True)
    def on_get__id(self, req: Request, resp: Response, _id: ObjectId):
        file_ = db.files.find_one({'_id': _id})
        if file_ is None:
            raise falcon.errors.HTTPNotFound(title='no such file found')
        if file_['kind'] == 'output':
            if not req.context.authenticated:
                raise falcon.errors.HTTPUnauthorized()
            project = db.projects.find_one({'_id': file_['project_id'],
                '$or':
                    [
                        {'employer._id': req.context.user_id},
                        {'employee._id': req.context.user_id}
                    ]
            })
            if project is None:
                raise falcon.errors.HTTPForbidden()
        file_path = os.path.join('uploads', 'files', str(_id))
        resp.stream = io.open(file_path, 'rb')
        resp.downloadable_as = file_['title']
        resp.content_length = os.path.getsize(file_path)
        resp.content_type = guess_type(file_['title'])[0]

    @falcon.before(auth, optional=True)
    @falcon.before(validate_req, {
        "project_id": {"type": "string", "required": True},
        "kind": {"type": "string", "regex": "^(input|output)$", "default": "input"}
    }, produce_filter=True, require_all=False)
    def on_get(self, req: Request, resp: Response):
        try:
            project_id = ObjectId(req.context.params['project_id'])
        except:
            raise falcon.errors.HTTPBadRequest(title='invalid project_id')
        req.context.filter['project_id'] = project_id
        if req.context.params['kind'] == 'output':
            if not req.context.authenticated:
                raise falcon.errors.HTTPUnauthorized()
            project = db.projects.find_one({'_id': project_id, 
                '$or':
                    [
                        {'employer._id': req.context.user_id},
                        {'employee._id': req.context.user_id}
                    ]
            })
            if project is None:
                raise falcon.errors.HTTPForbidden()
        files = db.files.find(req.context.filter)
        resp.media = list(files)


class MessageResource(object):
    @falcon.before(auth)
    @falcon.before(validate_req, {
        "project_id": {"type": "objectid"},
        "body": {"type": "string", "minlength": 1, "maxlength": 500}
    })
    def on_post(self, req: Request, resp: Response):
        project = db.projects.find_one({"_id": req.context.params['project_id'], 
            '$or':
                [
                    {'employer._id': req.context.user_id},
                    {'employee._id': req.context.user_id}
                ]
        })
        if project is None:
            raise falcon.errors.HTTPForbidden(title='no such project found for you')
        user = db.users.find_one({"_id": req.context.user_id}, {'_id': 1, 'name': 1})
        if user is None:
            raise falcon.errors.HTTPUnauthorized()
        message = {
            "project_id": req.context.params['project_id'],
            "body": req.context.params['body'],
            "creation_datetime": datetime.utcnow(),
            "sender": user,
            "seen": False,
        }
        result = db.messages.insert_one(message)
        resp.status = falcon.HTTP_CREATED
        resp.media = {"_id": result.inserted_id, 'project_id': message['project_id']}

    @falcon.before(auth)
    @falcon.before(validate_req, {
        "project_id": {"type": "string", "required": True},
        "skip": {"type": "integer", "coerce": int, "min": 0, "default": 0},
        "limit": {"type": "integer", "coerce": int, "min": 1, "default": LIMIT},
    }, produce_filter=True)
    def on_get(self, req: Request, resp: Response):
        try:
            project_id = ObjectId(req.context.params['project_id'])
        except:
            raise falcon.errors.HTTPBadRequest(title='invalid project_id')
        req.context.filter['project_id'] = project_id
        project = db.projects.find_one({"_id": project_id, 
            '$or':
                [
                    {'employer._id': req.context.user_id},
                    {'employee._id': req.context.user_id}
                ]
        })
        if project is None:
            raise falcon.errors.HTTPForbidden(title='no such project found for you')
        messages = db.messages.find(
            req.context.filter,
            limit=req.context.params['limit'], skip=req.context.params['skip']
        ).sort('creation_datetime', DESCENDING)
        messages = list(messages)
        messages.reverse()
        resp.media = messages 


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
    app.router_options.converters["ObjectId"] = ObjectIdConverter

    json_handler = falcon.media.JSONHandler(dumps=dumps, loads=loads,)
    form_handler = falcon.media.MultipartFormHandler()
    extra_handlers = {
        "application/json": json_handler,
        'multipart/formdata': form_handler
    }
    app.req_options.media_handlers.update(extra_handlers)
    app.resp_options.media_handlers.update(extra_handlers)

    test = TestResource()
    user = UserResource()
    code = CodeResource()
    token = TokenResource()
    project = ProjectResource()
    file_ = FileResource()
    messages = MessageResource()

    app.add_route("/v1/test", test)
    app.add_route("/v1/users", user)
    app.add_route("/v1/users/me", user, suffix="me")
    app.add_route("/v1/users/{name:user_name}", user, suffix="name")
    app.add_route("/v1/code", code)
    app.add_route("/v1/token", token)
    app.add_route("/v1/projects", project)
    app.add_route("/v1/projects/{_id:ObjectId}", project, suffix="_id")
    app.add_route('/v1/files', file_)
    app.add_route('/v1/files/{_id:ObjectId}', file_, suffix='_id')
    app.add_route('/v1/messages', messages)
    return app


app = create_app(is_testing=is_debugging)
