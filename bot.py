import os
import asyncio
import redis
import logging
import json
import sys

from hawk_python_sdk import Hawk
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, CallbackQuery, WebAppInfo, ContentType

load_dotenv()
work_dir = os.path.abspath(os.getcwd())

# sys.path.append("modules")
# from ldap_auth import ldap_logon

# hawk = Hawk(os.getenv("HAWK_key"))
bot = Bot(token=os.getenv("telegram_api_key"))
dp = Dispatcher()
webapp = WebAppInfo(url=os.getenv("webapp_url"))

def bot_config_read() -> dict:
	with open("./config.json") as config_file:
		return json.load(config_file)

def redis_connect() -> bool:
	config = bot_config_read()["databases"]["redis"]

	session_db_redis = redis.StrictRedis(
		host=config["url"],
		port=config["port"],
		password = os.getenv("redis_password"),
		decode_responses=True)
	return session_db_redis.ping()

@dp.message(CommandStart(), StateFilter(default_state))
async def command_start_handler(message: Message) -> None:
	await bot.delete_message(chat_id = message.chat.id, message_id = message.message_id)

	login_button = [KeyboardButton(text = f"Авторизироваться как {message.chat.username}", web_app = webapp)]
	login_keyboard = ReplyKeyboardMarkup(keyboard = [login_button], resize_keyboard=True)

	await message.answer(f"Привет-привет *{message.chat.username}* пожалуйста пройди авторизацию", parse_mode = 'Markdown', reply_markup = login_keyboard)

async def main() -> None:
	config = bot_config_read()

    logger = logging.getLogger(__name__)
	logging.basicConfig(
		level = logging.getLevelName(config["logs"]["level"].upper()),
		filename = config["logs"]["file"],
		filemode = "a",
		format="%(asctime)s %(levelname)s %(module)s %(message)s")

	if redis_connect() != True:
		print("Error redis connect")
		logging.critical("Error redis connect")
	else:
		print("Redis PONG")
		logging.debug("Redis PONG")
	print("Started")
	logging.info("Started")
	await dp.start_polling(bot)

if __name__ == "__main__":
	asyncio.run(main())