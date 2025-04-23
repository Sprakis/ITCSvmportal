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

sys.path.append("modules")
from ldap_auth import ldap_logon
from session_controller import new_session, update_session, exit_session

# hawk = Hawk(os.getenv("HAWK_key"))
bot = Bot(token=os.getenv("telegram_api_key"))
dp = Dispatcher()
webapp = WebAppInfo(url=os.getenv("webapp_url"))

admin_list = "Admin"

def bot_config_read() -> dict:
	with open("./config.json") as config_file:
		return json.load(config_file)

config = bot_config_read()["databases"]["redis"]
session_db_redis = redis.StrictRedis(
		host=config["url"],
		port=config["port"],
		password = os.getenv("redis_password"),
		db = os.getenv("redis_session_db"),
		decode_responses=True
)

def redis_connect() -> bool:
	return session_db_redis.ping()

@dp.message(CommandStart(), StateFilter(default_state))
async def command_start_handler(message: Message) -> None:
	await bot.delete_message(chat_id = message.chat.id, message_id = message.message_id)

	login_button = [KeyboardButton(text = f"Авторизироваться как {message.chat.username}", web_app = webapp)]
	login_keyboard = ReplyKeyboardMarkup(keyboard = [login_button], resize_keyboard=True)

	await message.answer(f"Привет-привет *{message.chat.username}* пожалуйста пройди авторизацию", parse_mode = 'Markdown', reply_markup = login_keyboard)


@dp.message(F.content_type == ContentType.WEB_APP_DATA)
async def web_app_logon(message: Message) -> None:
	try:
		for i in range(3):
			await bot.delete_message(chat_id = message.chat.id, message_id = message.message_id - i)
	except:
		pass

	login_button = [KeyboardButton(text = f"Авторизироваться как {message.chat.username}", web_app = webapp)]
	login_keyboard = ReplyKeyboardMarkup(keyboard = [login_button], resize_keyboard=True)

	credentionals = json.loads(message.web_app_data.data)
	chat_id = message.chat.id
	tg_username = message.chat.username
	ldap_access, ldap_access_level, ldap_username, ldap_fullname = ldap_logon(credentionals)
	
	report_button = InlineKeyboardButton(text = "Сообщить о проблеме (НЕ РЕАЛИЗОВАНО)⚠️", callback_data = "report_menu")
	end_session_button = InlineKeyboardButton(text = "Завершить сессию🚪", callback_data = "session_end")
	main_menu_keyboard_buttons_list = [[report_button], [end_session_button]]

	# temporary main menu keyboard
	main_menu_keyboard = InlineKeyboardMarkup(inline_keyboard = main_menu_keyboard_buttons_list)

	if ldap_access:
		if ldap_access_level == "User":
			keyboard = main_menu_keyboard
		elif ldap_access_level == "Admin":
			keyboard = main_menu_keyboard
		else:
			await bot.send_message(chat_id = chat_id, text = "К сожалению у вас нет доступа", reply_markup = login_keyboard)
		
		if new_session(session_db_redis, tg_username, chat_id, ldap_username, ldap_access_level):
			await bot.send_message(chat_id = chat_id, text = f"Добро пожаловать *{ldap_fullname}*!\nУровень доступа: _{ldap_access_level}_", parse_mode = 'Markdown', reply_markup = main_menu_keyboard)
		else:
			logging.debug(f"Ошибка открытия новой сессии для {ldap_username}")
			await bot.send_message(chat_id = chat_id, text = f"Произошла ошибка при открытии сессии😵‍💫. Пожалуйста обратитесь к администраторам:\n{admin_list}", parse_mode = 'Markdown', reply_markup = login_keyboard)
	else:
		await bot.send_message(chat_id = chat_id, text = "Неверный логин или пароль", reply_markup = login_keyboard)


@dp.callback_query(F.data == 'session_end')
async def end_user_session(callback: CallbackQuery) -> None:
	username = callback.from_user.username

	try:
		await bot.delete_message(chat_id = callback.from_user.id, message_id = callback.message.message_id)
	except:
		pass

	if exit_session(session_db_redis, username):
		login_button = [KeyboardButton(text = f"Авторизироваться как {username}", web_app = webapp)]
		login_keyboard = ReplyKeyboardMarkup(keyboard = [login_button], resize_keyboard=True)
		await bot.send_message(chat_id = callback.from_user.id, text = "Сессия успешно завершена. Пожалуйста пройди авторизацию", reply_markup = login_keyboard)
		logging.debug(f"Сессия пользователя {username} успешно завершена")
	else:
		await bot.send_message(chat_id = callback.from_user.id, text = "Ошибка при закрытии сессии😱\nПожалуйста, обратитесь к администратору")
		logging.error(f"Ошибка при ручном завершении сессии пользователем {username}")



async def main() -> None:
	config = bot_config_read()["logs"]

	logging.basicConfig(
		level = logging.getLevelName(config["level"].upper()),
		filename = config["file"],
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