import falcon
from bson.objectid import ObjectId
from bson.json_util import loads
from cerberus import Validator, TypeDefinition

from .jwt_user_id import token_to_user


def auth(req, resp, resource, params):
    """
        the route needs authentication.
        it produces user_id.
    """
    user_id = token_to_user(req.auth)
    if user_id == "":
        raise falcon.errors.HTTPUnauthorized()
    req.context.user_id = ObjectId(user_id)


def validate_req(
    req,
    resp,
    resource,
    params,
    schema: dict,
    require_all=True,
    purge_unknown=True,
    produce_filter=False,
):
    if req.method in ["POST", "PUT", "PATCH"]:
        if req.media is None:
            raise falcon.errors.HTTPUnsupportedMediaType(description="json is required")
        d = req.media
    elif req.method == "GET":
        d = req.params
    else:
        raise falcon.errors.HTTPMethodNotAllowed(
            ["POST", "PUT", "PATCH", "GET"],
            description="parameter validation is not implemented for this method",
        )

    objectid_type = TypeDefinition("objectid", (ObjectId,), ())
    Validator.types_mapping["objectid"] = objectid_type
    V = Validator(schema, require_all=require_all, purge_unknown=purge_unknown)

    d = V.normalized(d)
    req.context.params = d
    if not V.validate(d):
        raise falcon.errors.HTTPBadRequest(description=V.errors)
    if produce_filter:
        keys = d.keys()
        filter_keys = []
        for key in keys:
            if d[key] != "all" and key not in ["skip", "limit"]:
                filter_keys.append(key)
        filter_ = {}
        for filter_key in filter_keys:
            filter_[filter_key] = d[filter_key]
        req.context.filter = filter_
