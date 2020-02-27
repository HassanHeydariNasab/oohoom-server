import falcon
from cerberus import Validator
from bson.objectid import ObjectId
from jwt_user_id import token_to_user


def auth(req, resp, resource, params):
    """
        the route needs authentication.
        it produces user_id.
    """
    user_id = token_to_user(req.auth)
    if user_id == "":
        raise falcon.errors.HTTPUnauthorized()
    req.context.user_id = ObjectId(user_id)


def validate_req(req, resp, resource, params, schema, require_all=True):
    if req.media is None:
        raise falcon.errors.HTTPUnsupportedMediaType(description="json is required")
    V = Validator(schema, require_all=True)
    if not V.validate(req.media):
        raise falcon.errors.HTTPBadRequest(description=V.errors)

