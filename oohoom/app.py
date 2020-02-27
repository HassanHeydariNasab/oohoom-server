import os
import string
import datetime
import falcon
import r_code
from jwt_user_id import user_to_token
from random import SystemRandom
from pymongo import MongoClient
from kavenegar import KavenegarAPI
from bson.objectid import ObjectId
from pymongo.collection import ReturnDocument
from local_config import KAVENEGAR_APIKEY
from utils import normalized_mobile
from hooks import auth, validate_req

client = MongoClient()
db = client.oohoom


class UserResource(object):
    @falcon.before(auth)
    def on_get(self, req, resp):
        user = db.users.find_one({"_id": req.context.user_id})
        # a rare case
        if user is None:
            raise falcon.errors.HTTPNotFound(description="user not found")
        user["_id"] = str(user["_id"])
        resp.media = user

    # registration
    @falcon.before(
        validate_req,
        {
            "mobile": {"type": "string", "minlength": 5, "maxlength": 30},
            "code": {"type": "string"},
            "name": {"type": "string", "maxlength": 36, "minlength": 1},
        },
    )
    def on_post(self, req, resp):
        req.media["mobile"] = normalized_mobile(req.media.get("mobile"))
        if not r_code.is_valid(req.media.get("mobile"), req.media.get("code")):
            raise falcon.errors.HTTPUnauthorized(
                description="mobile or code is invalid"
            )
        if (
            db.users.find_one(
                {"mobile": req.media.get("mobile")}, projection={"mobile": 1}
            )
            is not None
        ):
            raise falcon.errors.HTTPConflict(description="user already exists")
        result = db.users.insert_one(
            {"mobile": req.media.get("mobile"), "name": req.media.get("name")}
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
            raise falcon.errors.HTTPUnauthorized(
                description="mobile or code is invalid"
            )
        user = db.users.find_one({"mobile": req.media.get("mobile")})
        if user is None:
            raise falcon.errors.HTTPUnauthorized(
                description="mobile or code is invalid"
            )
        token = user_to_token(str(user["_id"]))
        resp.media = {"token": token}


app = falcon.API()

user = UserResource()
code = CodeResource()
token = TokenResource()

app.add_route("/v1/user", user)
app.add_route("/v1/code", code)
app.add_route("/v1/token", token)
