import asyncio
import logging
import secrets
from datetime import datetime
from typing import Optional

import aiostream as aiostream
import bitmath
import dateparser as dateparser
import motor
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseSettings

from utils import post_to_hastebin, convert


class Settings(BaseSettings):
    webhook_url: str
    host: str = "0.0.0.0"
    port: int
    webhook_path: str = "/" + secrets.token_urlsafe(32)

    mongodb_uri: str = "localhost"
    mongodb_username: Optional[str] = None
    mongodb_password: Optional[str] = None
    mongodb_database: str

    create_indexes: int = 1

    api_key: str
    proxy: Optional[str] = None
    chat: str
    owner_id: int

    class Config:
        env_file = ".env"


settings = Settings()

loop = asyncio.get_event_loop()

client = AsyncIOMotorClient(settings.mongodb_uri, io_loop=loop)

db = client.get_database(settings.mongodb_database).get_collection("messages")


async def create():
    if settings.create_indexes == 1:
        await db.create_index([("from.username", 1)])
        await db.create_index([("from.id", 1)])
        await db.create_index([("from.first_name", 1)])


loop.run_until_complete(create())

API_TOKEN = settings.api_key


# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN, proxy=settings.proxy)
dp = Dispatcher(bot)


@dp.message_handler(commands=["rec_status"])
async def status(message: types.Message):
    if message.from_user.id != int(settings.owner_id):
        return
    text = f"""Примерное количество сообщений: {await db.estimated_document_count()}
Примерный размер базы: {(bitmath.Byte(451) * (await db.estimated_document_count())).best_prefix()}"""
    await message.answer(text)


@dp.message_handler(commands=["rec_logs"])
async def logs(message: types.Message):
    """
    /rec_logs <username> [<from_date>-<to_date>]
    """
    if message.from_user.id not in [
        a.user.id for a in await (await bot.get_chat(settings.chat)).get_administrators()
    ]:
        return

    from_date, to_date = None, datetime.now()

    try:
        from_date, to_date = map(dateparser.parse, message.text.split(" ", maxsplit=2)[2].split("-"))
    except IndexError:
        pass

    date_filter = {}
    if from_date is not None:
        date_filter["$gte"] = from_date
    if to_date is not None:
        date_filter["$lte"] = to_date

    print(date_filter)

    try:
        user = message.text.split(" ")
        if len(user) <= 1:
            raise IndexError()
        key = "from.id" if not user[1].startswith("@") else "from.username"
        user = user[1]
        if user == "-":
            raise IndexError()
    except IndexError:
        if message.reply_to_message is None:
            return
        user = str(message.reply_to_message.from_user.id)
        key = "from.id"
    user = user.lstrip("@")
    user = int(user) if user.isdigit() else user
    data = f"Логи для {user}\n\n"
    async with aiostream.streamcontext(db.find({key: user, "date": date_filter})) as st:
        async for item in st:
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
        await db.insert_one(convert(message))


@dp.edited_message_handler()
async def edit_msg(message: types.Message):
    if message.chat.username == settings.chat:
        await db.insert_one(convert(message))


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
        host=settings.host,
        port=settings.port,
        loop=loop,
    )
