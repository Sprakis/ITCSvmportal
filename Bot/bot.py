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
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, CallbackQuery, WebAppInfo, ContentType

load_dotenv()
work_dir = os.path.abspath(os.getcwd())

sys.path.append("modules")
from ldap_auth import ldap_logon
from session_controller import new_session, update_session, exit_session, load_user_data, check_session

# hawk = Hawk(os.getenv("HAWK_key"))

admin_list = "Admin"

def bot_config_read() -> dict:
	with open("./config.json") as config_file:
		return json.load(config_file)

config = bot_config_read()["databases"]["redis"]
db_redis = f"redis://:{os.getenv("redis_password")}@{config["url"]}:{config["port"]}/"

session_db_redis = redis.from_url(db_redis + os.getenv("redis_session_db"))

def redis_connect() -> bool:
	return session_db_redis.ping()

bot = Bot(token=os.getenv("telegram_api_key"))
storage = RedisStorage.from_url(db_redis + os.getenv("redis_FSM_db"))
dp = Dispatcher(storage = storage)
webapp = WebAppInfo(url=os.getenv("webapp_url"))


class main_states(StatesGroup):
	menu = State()

def menu_buttons_build(access_level: str, path: str):
	# Вм меню
		# Создание ВМ
		# Ренейм ВМ
		# Удаление ВМ
	# Сети
		# Присвоение ip адреса на что-то
		# Удаление ip адреса с чего-то
		# Перенос ip адреса с чего-то на что-то
		# Изменение ip адреса на чем-то
		# Выдача доступа в интернет для ip адреса
	# admin_plane_button = InlineKeyboardButton(text = "Панель администратора", callback_data = "admin_plane_menu") # Admin plane | Заявки
		# Список назначенных заявок + там же решение их + отправка на доработку
		# Список открытых заявок всего
		# История назначенных заявок
		# Tasks
		# Обявление
	
	# report_button = InlineKeyboardButton(text = "Сообщить о проблеме (НЕ РЕАЛИЗОВАНО)⚠️", callback_data = "report_menu")
	# notifications_center_button = InlineKeyboardButton(text = "Центр уведомлений (НЕ РЕАЛИЗОВАНО)⚠️", callback_data = "notifications_center_menu")
	# end_session_button = InlineKeyboardButton(text = "Завершить сессию🚪", callback_data = "session_end")
	
	# main_buttons = [[report_button], [notifications_center_button], [end_session_button]]
	
	if path == "main_menu":
		admin_plane_button = InlineKeyboardButton(text = "Панель администратора", callback_data = "admin_plane_menu")

		report_button = InlineKeyboardButton(text = "Сообщить о проблеме (НЕ РЕАЛИЗОВАНО)⚠️", callback_data = "report_menu")
		notifications_center_button = InlineKeyboardButton(text = "Центр уведомлений (НЕ РЕАЛИЗОВАНО)⚠️", callback_data = "notifications_center_menu")
		end_session_button = InlineKeyboardButton(text = "Завершить сессию🚪", callback_data = "session_end")

		main_buttons = [[report_button], [notifications_center_button], [end_session_button]]
		if access_level == "Admin":
			main_buttons_finish_list = [[admin_plane_button]] + main_buttons
		else:
			main_buttons_finish_list = main_buttons
	
	return InlineKeyboardMarkup(inline_keyboard = main_buttons_finish_list)

async def clean_message(chat_id: int, message_id: int, count: int):
	try:
		for i in range(count):
			await bot.delete_message(chat_id = chat_id, message_id = message_id - i)
	except:
		pass

@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
	await clean_message(message.chat.id, message.message_id, 3)
	await bot.send_message(chat_id = message.chat.id, text = f"Это *ITCS* _VM portal_ ~~bot~~", parse_mode = 'Markdown')

	current_state = await state.get_state()

	if current_state and check_session(session_db_redis, message.chat.username):
		await state.set_state(main_states.menu)
		update_session(session_db_redis, message.chat.username)
		await bot.send_message(chat_id = message.chat.id, text = f"Меню доступно через команду /menu или через контекстное меню бота", parse_mode = 'Markdown')
	else:
		login_button = [KeyboardButton(text = f"Авторизироваться как {message.chat.username}", web_app = webapp)]
		login_keyboard = ReplyKeyboardMarkup(keyboard = [login_button], resize_keyboard=True)

		await state.clear()
		await message.answer(f"Привет-привет, *{message.chat.username}*! Пожалуйста пройди авторизацию", parse_mode = 'Markdown', reply_markup = login_keyboard)



@dp.message(F.content_type == ContentType.WEB_APP_DATA, StateFilter(default_state))
async def web_app_logon(message: Message, state: FSMContext) -> None:
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
	ldap_access, access_level, ldap_username, ldap_fullname = ldap_logon(credentionals)

	if ldap_access:
		if access_level == "User" or access_level == "Admin":
			keyboard = menu_buttons_build(access_level, "main_menu")
		else:
			await bot.send_message(chat_id = chat_id, text = "К сожалению у вас нет доступа", reply_markup = login_keyboard)
		
		if new_session(session_db_redis, tg_username, chat_id, ldap_username, ldap_fullname, access_level):
			await state.set_state(main_states.menu)
			await bot.send_message(chat_id = chat_id, text = f"Добро пожаловать *{ldap_fullname}*!\nУровень доступа: _{access_level}_", parse_mode = 'Markdown', reply_markup = keyboard)
		else:
			logging.debug(f"Ошибка открытия новой сессии для {ldap_username}")
			await bot.send_message(chat_id = chat_id, text = f"Произошла ошибка при открытии сессии😵‍💫. Пожалуйста обратитесь к администраторам:\n{admin_list}", parse_mode = 'Markdown', reply_markup = login_keyboard)
	else:
		await bot.send_message(chat_id = chat_id, text = "Неверный логин или пароль", reply_markup = login_keyboard)


@dp.message(Command(commands=["menu"]))
async def main_menu(message: Message, state: FSMContext):
	try:
		for i in range(3):
			await bot.delete_message(chat_id = message.chat.id, message_id = message.message_id - i)
	except:
		pass
	current_state = await state.get_state()
	
	if current_state and check_session(session_db_redis, message.chat.username):
		update_session(session_db_redis, message.chat.username)
		await state.set_state(main_states.menu)
		user_data = load_user_data(session_db_redis, message.chat.username, ["ldap_fullname", "access_level"])
		await bot.send_message(chat_id = message.chat.id, text = f"Добро пожаловать *{user_data["ldap_fullname"]}*!\nУровень доступа: _{user_data["access_level"]}_", parse_mode = 'Markdown', reply_markup = menu_buttons_build(user_data["access_level"], "main_menu"))
	else:
		login_button = [KeyboardButton(text = f"Авторизироваться как {message.chat.username}", web_app = webapp)]
		login_keyboard = ReplyKeyboardMarkup(keyboard = [login_button], resize_keyboard=True)

		await state.clear()
		await message.answer(f"Привет-привет *{message.chat.username}* пожалуйста пройди авторизацию", parse_mode = 'Markdown', reply_markup = login_keyboard)


		


@dp.callback_query(F.data == 'session_end', StateFilter(main_states.menu))
async def end_user_session(callback: CallbackQuery, state: FSMContext) -> None:
	username = callback.from_user.username

	try:
		await bot.delete_message(chat_id = callback.from_user.id, message_id = callback.message.message_id)
	except:
		pass

	if exit_session(session_db_redis, username):
		login_button = [KeyboardButton(text = f"Авторизироваться как {username}", web_app = webapp)]
		login_keyboard = ReplyKeyboardMarkup(keyboard = [login_button], resize_keyboard=True)

		await bot.send_message(chat_id = callback.from_user.id, text = "Сессия успешно завершена. Пожалуйста пройди авторизацию", reply_markup = login_keyboard)
		await state.clear()

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