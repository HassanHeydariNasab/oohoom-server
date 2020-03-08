from pymongo import MongoClient

client = MongoClient()
db = client.oohoom

db.create_collection(
    "users",
    validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["mobile", "name"],
            "properties": {
                "mobile": {"bsonType": "string", "minLength": 5, "maxLength": 30},
                "name": {"bsonType": "string", "minLength": 1, "maxLength": 36},
            },
        }
    },
)
