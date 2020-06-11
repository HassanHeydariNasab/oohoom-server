from re import match
from falcon.routing import BaseConverter
from bson import ObjectId


class UserNameConverter(BaseConverter):
    def convert(self, value: str):
        value = value.lower()
        if match("^(?!(me)$)[a-z0-9_]+$", value) is not None:
            return value
        return None

class ObjectIdConverter(BaseConverter):
    def convert(self, value: str):
        value = value.lower()
        try:
            return ObjectId(value)
        except:
            return None

