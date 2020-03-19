from re import match
from falcon.routing import BaseConverter


class UserNameConverter(BaseConverter):
    def convert(self, value: str):
        value = value.lower()
        if match("^(?!(me)$)[a-z0-9_]+$", value) is not None:
            return value
        return None
