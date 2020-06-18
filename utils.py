from datetime import datetime

import orjson
import requests
from aiogram import types


def convert(message: types.Message):
    data = orjson.loads(orjson.dumps(message.to_python()))
    data = {
        key: datetime.fromtimestamp(value).isoformat() if key == "date" else value
        for key, value in data.items()
    }
    if data.get("edit_date") is not None:
        data["edit_date"] = message.edit_date
    data["date"] = message.date
    return data


def decode(message, append: str = ""):
    return (
        "@"
        + str(message["from"].get("username", None) or message["from"]["id"])
        + append
    )


def post_to_hastebin(text: str):
    return (
        "https://hastebin.com/"
        + requests.post("https://hastebin.com/documents", text.encode("utf-8")).json()[
            "key"
        ]
    )