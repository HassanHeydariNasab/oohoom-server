from pymongo import MongoClient


def init(is_testing=False):
    if is_testing:
        client = MongoClient()
        client.drop_database("test_oohoom")
        db = client.test_oohoom
    else:
        is_confirmed = "no"
        is_confirmed = input("Delete main database? (yes / [no]) :  ")
        if is_confirmed != "yes":
            print("bye")
            return False
        client = MongoClient()
        client.drop_database("oohoom")
        print("deleted")
        db = client.oohoom

    user_name = {
        "bsonType": "string",
        "minLength": 1,
        "maxLength": 36,
        "pattern": "^[a-z0-9_]+$",
    }

    db.create_collection(
        "users",
        validator={
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["mobile", "name", "role", "state", "skills"],
                "properties": {
                    "mobile": {"bsonType": "string", "minLength": 5, "maxLength": 30},
                    "name": user_name,
                    "role": {"bsonType": "string", "enum": ["employer", "employee"]},
                    "state": {"bsonType": "string", "enum": ["idle", "busy"]},
                    "skills": {"bsonType": "array"},
                },
            }
        },
    )

    db.users.create_index('mobile', unique=True)
    db.users.create_index('name', unique=True)

    db.create_collection(
        "projects",
        validator={
            "$jsonSchema": {
                "bsonType": "object",
                "required": [
                    "title",
                    "description",
                    "employer",
                    "employee",
                    "state",
                    "creation_datetime",
                ],
                "properties": {
                    "title": {"bsonType": "string", "minLength": 1, "maxLength": 88},
                    "description": {
                        "bsonType": "string",
                        "minLength": 0,
                        "maxLength": 500,
                    },
                    "employer": {
                        "bsonType": "object",
                        "required": ["_id", "name"],
                        "properties": {
                            "_id": {"bsonType": "objectId"},
                            "name": user_name,
                        },
                    },
                    "employee": {
                        "bsonType": "object",
                        "required": ["_id", "name"],
                        "properties": {
                            "_id": {"bsonType": "objectId"},
                            "name": user_name,
                        },
                    },
                    "state": {"bsonType": "string", "enum": ["new", "done", "closed"],},
                    "creation_datetime": {"bsonType": "date"},
                },
            }
        },
    )

    db.create_collection(
        "messages",
        validator={
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["project", "sender", "creation_datetime", "seen", "body"],
                "properties": {
                    "project": {"bsonType": "objectId"},
                    "sender": {
                        "bsonType": "object",
                        "required": ["_id", "name"],
                        "properties": {
                            "_id": {"bsonType": "objectId"},
                            "name": user_name,
                        },
                    },
                    "creation_datetime": {"bsonType": "date"},
                    "seen": {"bsonType": "bool"},
                    "body": {"bsonType": "string", "minLength": 1, "maxLength": 500},
                },
            }
        },
    )

    db.create_collection(
        "files",
        validator={
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["project", "kind", "creation_datetime", "title"],
                "properties": {
                    "project": {"bsonType": "objectId"},
                    "kind": {"bsonType": "string", "enum": ["input", "output"]},
                    "creation_datetime": {"bsonType": "date"},
                    "title": {"bsonType": "string", "minLength": 1, "maxLength": 88},
                },
            }
        },
    )
    print("created")
    return True
