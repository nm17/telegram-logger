import logging
import secrets
from datetime import datetime
from typing import Optional

import orjson as orjson
import pymongo
import requests
from aiogram import Bot, Dispatcher, executor, types
from aiogram.utils.executor import start_webhook
from pydantic import BaseSettings
import bitmath

from pymongo import MongoClient


class Settings(BaseSettings):
    webhook_url: str
    host: str = "0.0.0.0"
    port: int
    webhook_path: str = "/" + secrets.token_urlsafe(32)

    mongodb_host: str = "localhost"
    mongodb_username: Optional[str] = None
    mongodb_password: Optional[str] = None

    create_indexes: int = 1

    api_key: str
    proxy: Optional[str] = None
    chat: str
    owner_id: int

    class Config:
        env_file = ".env"


settings = Settings()

client = MongoClient(
    host=settings.mongodb_host,
    username=settings.mongodb_username,
    password=settings.mongodb_username,
)

db = client.get_database("logger").get_collection("messages")
if settings.create_indexes == 1:
    db.create_index([("from.username", pymongo.ASCENDING)])
    db.create_index([("from.id", pymongo.ASCENDING)])
    db.create_index([("from.first_name", pymongo.ASCENDING)])

API_TOKEN = settings.api_key


# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN, proxy=settings.proxy)
dp = Dispatcher(bot)


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


@dp.message_handler(commands=["rec_status"])
async def status(message: types.Message):
    if message.from_user.id != int(settings.owner_id):
        return
    text = f"""Примерное количество сообщений: {db.estimated_document_count()}
Примерный размер базы: {(bitmath.Byte(451) * db.estimated_document_count()).best_prefix()}"""
    await message.answer(text)


@dp.message_handler(commands=["rec_logs"])
async def logs(message: types.Message):
    if message.from_user.id not in [
        a.user.id
        for a in [*(await message.chat.get_administrators()), settings.owner_id]
    ]:
        return
    try:
        user = message.text.split(" ")
        if len(user) == 1:
            raise IndexError
        key = "from.id" if user.startswith("@") else "from.username"
    except IndexError:
        if message.reply_to_message is None:
            return
        user = str(message.reply_to_message.from_user.id)
        key = "from.id"
    user = int(user) if user.isdigit() else user
    data = f"Логи для {user}\n\n"
    for item in db.find({key: user}):
        reply = item.get("reply_to_message", {})
        data += (
            f"[{item['date']}, {item['message_id']}] "
            f"{reply.get('text', '')} -- {item['text']}\n"
        )

    url = post_to_hastebin(data)
    await message.reply(url, disable_web_page_preview=True)


@dp.message_handler()
async def msg(message: types.Message):
    if message.chat.username == settings.chat:
        db.insert_one(convert(message))


@dp.edited_message_handler()
async def edit_msg(message: types.Message):
    if message.chat.username == settings.chat:
        db.insert_one(convert(message))


async def on_startup(dp):
    await bot.set_webhook(settings.webhook_url + settings.webhook_path)


async def on_shutdown(dp):
    await bot.delete_webhook()


logging.basicConfig(level=logging.DEBUG)

if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=settings.webhook_path,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host="127.0.0.1",
        port=9000,
    )
