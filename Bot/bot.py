import os
import asyncio
import logging
import json
import sys
import datetime
import ipaddress

from hawk_python_sdk import Hawk

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, CallbackQuery, WebAppInfo, ContentType
from aiogram.utils.media_group import MediaGroupBuilder

load_dotenv()
work_dir = os.path.abspath(os.getcwd())

sys.path.append("modules")
from ldap_auth import ldap_logon
from session_controller import new_session, update_session, exit_session, load_user_data, check_session
from netbox_con import get_ip_info, get_vm_info
from paloalto_con import get_ip_net_info

# hawk = Hawk(os.getenv("HAWK_key"))

admin_list = "Admin"

def bot_config_read() -> dict:
	with open("./config.json") as config_file:
		return json.load(config_file)

config = bot_config_read()["databases"]


import redis

redis_config = config["redis"]
db_redis = f"redis://:{os.getenv("redis_password")}@{redis_config["url"]}:{redis_config["port"]}/"
session_db_redis = redis.from_url(db_redis + os.getenv("redis_session_db"))
tmp_db_redis = redis.from_url(db_redis + os.getenv("redis_tmp_db"))

def redis_connect() -> bool:
	return session_db_redis.ping()


import psycopg2

psql_config = config["psql"]
psql_conn = psycopg2.connect(user = os.getenv("postsql_username"),
							password = os.getenv("postsql_password"),
							host = psql_config["url"],
							port = psql_config["port"],
							dbname = os.getenv("postsql_database"))
psql_conn.set_session(autocommit=True)
psql_cursor = psql_conn.cursor()


def psql_connect() -> str:
	psql_cursor.execute("SELECT version();")
	return psql_cursor.fetchone()

# psql check_tables
psql_cursor.execute("""select * from information_schema.tables where table_name='Admins table';""")
if bool(psql_cursor.rowcount):
	print("Admins table - Exist")
else:
	psql_cursor.execute("""CREATE TABLE public."Admins table" (
	username character varying(24) NOT NULL,
	chat_id bigint NOT NULL
);""")
	print("Admins table - Created")

psql_cursor.execute("""select * from information_schema.tables where table_name='Reports table';""")
if bool(psql_cursor.rowcount):
	print("Reports table - Exist")
else:
	psql_cursor.execute("""CREATE TABLE public."Reports table" (
	text character varying(4096) NOT NULL,
	status character varying(6) NOT NULL,
	attachments_hashs text,
	chat_id bigint NOT NULL,
	username character varying(24) NOT NULL,
	"ID_rep" bigint NOT NULL,
	PRIMARY KEY ("ID_rep")
);""")
	psql_cursor.execute("""CREATE SEQUENCE public."Reports table_ID_rep_seq" CYCLE INCREMENT 1 START 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1;""")
	psql_cursor.execute("""ALTER SEQUENCE public."Reports table_ID_rep_seq" OWNED BY public."Reports table"."ID_rep";""")
	psql_cursor.execute("""ALTER TABLE IF EXISTS public."Reports table" ALTER COLUMN "ID_rep" SET DEFAULT nextval('"Reports table_ID_rep_seq"'::regclass);""")
	print("Reports table - Created")

psql_cursor.execute("""select * from information_schema.tables where table_name='Requests table';""")
if bool(psql_cursor.rowcount):
	print("Requests table - Exist")
else:
	psql_cursor.execute("""CREATE TABLE public."Requests table" (
	"ID" bigint NOT NULL,
	type character varying(6) NOT NULL,
	owner_ldap_fullname character varying(30),
	owner_chat_id integer NOT NULL,
	owner_username character varying(30) NOT NULL,
	PRIMARY KEY ("ID")
);""")
	psql_cursor.execute("""CREATE SEQUENCE public."Requests table_ID_seq" CYCLE INCREMENT 1 START 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1;""")
	psql_cursor.execute("""ALTER SEQUENCE public."Requests table_ID_seq" OWNED BY public."Requests table"."ID";""")
	psql_cursor.execute("""ALTER TABLE IF EXISTS public."Requests table" ALTER COLUMN "ID" SET DEFAULT nextval('"Requests table_ID_seq"'::regclass);""")
	print("Requests table - Created")

psql_cursor.execute("""select * from information_schema.tables where table_name='Tasks table';""")
if bool(psql_cursor.rowcount):
	print("Tasks table - Exist")
else:
	psql_cursor.execute("""CREATE TABLE public."Tasks table" (
    id bigint NOT NULL,
    type character varying(100) NOT NULL,
    status character varying(12) NOT NULL,
    owner character varying(100),
    owner_id bigint NOT NULL,
    start_date character varying(30) NOT NULL,
    last_change_date character varying(30) NOT NULL,
    data text NOT NULL,
    comment character varying(100),
    PRIMARY KEY (id)
);""")
	psql_cursor.execute("""CREATE SEQUENCE public."Tasks table_id_seq" CYCLE INCREMENT 1 START 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1;""")
	psql_cursor.execute("""ALTER SEQUENCE public."Tasks table_id_seq" OWNED BY public."Tasks table"."id";""")
	psql_cursor.execute("""ALTER TABLE IF EXISTS public."Tasks table" ALTER COLUMN "id" SET DEFAULT nextval('"Tasks table_id_seq"'::regclass);""")
	print("Tasks table - Created")

psql_cursor.execute("""select * from information_schema.tables where table_name='Users table';""")
if bool(psql_cursor.rowcount):
	print("Users table - Exist")
else:
	psql_cursor.execute("""CREATE TABLE public."Users table" (
    username character varying NOT NULL,
    chat_id bigint NOT NULL,
    domain_username character varying NOT NULL
);""")
	print("Users table - Created")

bot = Bot(token=os.getenv("telegram_api_key"))
storage = RedisStorage.from_url(db_redis + os.getenv("redis_FSM_db"))
dp = Dispatcher(storage = storage)
webapp = WebAppInfo(url=os.getenv("webapp_url"))

class network(StatesGroup):
	menu = State()
	add_ip_form = State()
	internet_access = State()
	internet_access_ip = State()
	internet_access_vm = State()
	internet_resp = State()
	status_ip = State()
	status_ip_ip = State()
	status_ip_vm = State()

class admin_plane(StatesGroup):
	menu = State()
	announcement = State()
	view_all_tickets = State()

class main_states(StatesGroup):
	menu = State()

class send_report_states(StatesGroup):
	print_text_report = State()
	media_verify = State()
	media_add = State()
	media_del = State()
	verify_report = State()

# Service functions
def menu_buttons_build(access_level: str, path: str):
	back_button = InlineKeyboardButton(text = "Назад 🔙", callback_data = "back")
	match path:
		case "back_only":
			buttons_finish_list = [[back_button]]

		case "main_menu":

			network_menu_button = InlineKeyboardButton(text = "Сети 🌐", callback_data = "network_menu")
			
			admin_plane_button = InlineKeyboardButton(text = "Панель администратора 👑", callback_data = "admin_plane_menu")

			# tasks_center_button = InlineKeyboardButton(text = "Просмотр запланированных задач 🗓(НЕ РЕАЛИЗОВАНО)⚠️", callback_data = "notifications_center_menu")

			report_button = InlineKeyboardButton(text = "Сообщить о проблеме 📢", callback_data = "report_menu")

			last_update_button = InlineKeyboardButton(text = "Узнать о последнем обновлени ❔", callback_data = "last_update")
			
			end_session_button = InlineKeyboardButton(text = "Завершить сессию 🚪", callback_data = "session_end")

			main_buttons = [[network_menu_button], [report_button], [last_update_button], [end_session_button]]
			if access_level == "Admin":
				buttons_finish_list = [[admin_plane_button]] + main_buttons
			else:
				buttons_finish_list = main_buttons
		
		case "report_preview":
			change_text_button = InlineKeyboardButton(text = "Правка текста", callback_data = "report_menu")
			change_picture_button = InlineKeyboardButton(text = "Изменить вложения", callback_data = "change_picture")
			send_report_button = InlineKeyboardButton(text = "Отправить сообщение", callback_data = "send_report")

			buttons_finish_list = [[change_text_button], [change_picture_button], [send_report_button], [back_button]]

		case "admin_plane":
			all_tickets_button = InlineKeyboardButton(text = "Все заявки(НЕ РЕАЛИЗОВАНО)⚠️", callback_data = "all_tickets_0")
			announcement_button = InlineKeyboardButton(text = "Подача объявления", callback_data = "announcement")
			buttons_finish_list = [[all_tickets_button], [announcement_button], [back_button]]

		case "all_tickets":
			buttons_finish_list = [
				InlineKeyboardButton(text = "<<", callback_data = "all_tickets_slide-left"),
				InlineKeyboardButton(text = ">>", callback_data = "all_tickets_slide-right")
			], [
				InlineKeyboardButton(text = "Поиск по номеру тикета", callback_data = "all_ticket-search")
			], [
				back_button
			]
		
		case "announcement_preview":
			announcement_apply_button = InlineKeyboardButton(text = "Отправить объявление!", callback_data = "announcement_apply")
			buttons_finish_list = [[announcement_apply_button], [back_button]]
		
		case "network_menu":
			add_ip = InlineKeyboardButton(text = "Выделение IP адреса ➕ (В разработке)⚠️", callback_data = "network_add_ip")
			clean_ip = InlineKeyboardButton(text = "Освобождение IP ➖ (В разработке)⚠️", callback_data = "clean_ip")
			move_ip = InlineKeyboardButton(text = "Перенос IP адреса 📦 (В разработке)⚠️", callback_data = "move_ip")
			change_ip = InlineKeyboardButton(text = "Изменение IP 🔄 (В разработке)⚠️", callback_data = "change_ip")
			internet_access = InlineKeyboardButton(text = "Настройка доступа в интернет 🌐", callback_data = "internet_access")
			status_ip = InlineKeyboardButton(text = "Узнать статус IP 🤔", callback_data="status_ip")

			# buttons_finish_list = [[add_ip], [clean_ip], [move_ip], [change_ip], [internet_access], [status_ip], [back_button]]
			buttons_finish_list = [[internet_access], [status_ip], [back_button]]

		case "network_internet_access":
			internet_access_ip = InlineKeyboardButton(text = "Настройка по IP 🌐", callback_data="internet_ip")
			internet_access_vm = InlineKeyboardButton(text = "Настройка по имени машины 💻", callback_data="internet_vm")

			buttons_finish_list = [[internet_access_ip], [internet_access_vm], [back_button]]

		case "network_menu_status":
			info_by_ip = InlineKeyboardButton(text = "Информация по IP 🌐", callback_data="status_ip_ip")
			info_by_vm = InlineKeyboardButton(text = "Информация об оборудовании или виртуальной машине 💻 (В разработке)⚠️", callback_data="status_ip_vm")

			buttons_finish_list = [[info_by_ip], [info_by_vm], [back_button]]
	
	return InlineKeyboardMarkup(inline_keyboard = buttons_finish_list)

async def clean_message(chat_id: int, message_id: int, count: int) -> None:
	for i in range(count):
		try:
			await bot.delete_message(chat_id = chat_id, message_id = message_id - i)
		except:
			pass

async def end_session_notify(message: Message, state: FSMContext) -> None:
	login_button = [KeyboardButton(text = f"Авторизироваться как {message.chat.username}", web_app = webapp)]
	login_keyboard = ReplyKeyboardMarkup(keyboard = [login_button], resize_keyboard=True)

	await state.clear()
	await message.answer(f"Привет-привет *{message.chat.username}* пожалуйста пройди авторизацию", parse_mode = 'Markdown', reply_markup = login_keyboard)

@dp.message(F.content_type == ContentType.WEB_APP_DATA)
async def web_app_logon(message: Message, state: FSMContext) -> None:
		
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
			await clean_message(message.chat.id, message.message_id, 3)
			return
		
		if new_session(session_db_redis, tg_username, chat_id, ldap_username, ldap_fullname, access_level):
			await state.set_state(main_states.menu)
			await bot.send_message(chat_id = chat_id, text = f"Добро пожаловать *{ldap_fullname}*!\nУровень доступа: _{access_level}_", parse_mode = 'Markdown', reply_markup = keyboard)
			update_admins_table(access_level, tg_username, chat_id)
			update_users_table(tg_username, chat_id, ldap_fullname)
		else:
			logging.debug(f"Ошибка открытия новой сессии для {ldap_username}")
			await bot.send_message(chat_id = chat_id, text = f"Произошла ошибка при открытии сессии😵‍💫. Пожалуйста обратитесь к администраторам:\n{admin_list}", parse_mode = 'Markdown', reply_markup = login_keyboard)
	else:
		await bot.send_message(chat_id = chat_id, text = "Неверный логин или пароль", reply_markup = login_keyboard)
	
	await clean_message(message.chat.id, message.message_id, 3)

@dp.callback_query(F.data == "delete_notification")
async def delete_notification(callback: CallbackQuery) -> None:
	await clean_message(callback.from_user.id, callback.message.message_id, 1)

def update_admins_table(access_level, tg_username, chat_id) -> None:
	psql_cursor.execute(f"""SELECT chat_id FROM "Admins table" WHERE chat_id = '{chat_id}'""")
	if psql_cursor.fetchone():
		logging.debug(f"Пользователь {tg_username}:{chat_id} найден среди администраторов")
		if access_level == "User":
			psql_cursor.execute(f"""DELETE FROM "Admins table" WHERE chat_id = '{chat_id}'""")
			logging.debug(f"Пользователь {tg_username}:{chat_id} удален из списка администраторов")
	else:
		if access_level == "Admin":
			psql_cursor.execute(f"""INSERT INTO "Admins table" (username, chat_id) VALUES ('{tg_username}','{chat_id}')""")
			logging.debug(f"Пользователь {tg_username}:{chat_id} добавлен в список администраторов")

def update_users_table(tg_username: str, chat_id: int, ldap_fullname: str) -> None:
	psql_cursor.execute(f"""SELECT chat_id FROM "Users table" WHERE chat_id = '{chat_id}'""")
	result = psql_cursor.fetchone()
	if result:
		logging.debug(f"Пользователь {tg_username}:{chat_id} найден в Users")
		if (result[0] == tg_username and result[2] == ldap_fullname):
			logging.debug(f"Изменения в Users для {tg_username}:{chat_id} не требуются")
		else:
			logging.debug(f"Пользователь {tg_username}:{chat_id} обновлен")
			psql_cursor.execute(f"""UPDATE "Users table" SET username = '{tg_username}', domain_username = '{ldap_fullname}' WHERE chat_id = '{chat_id}'""")
	else:
		logging.debug(f"Пользователь {tg_username}:{chat_id} не найден в Users и будет создан")
		psql_cursor.execute(f"""INSERT INTO "Users table" (username, chat_id, domain_username) VALUES ('{tg_username}','{chat_id}','{ldap_fullname}')""")

async def send_report(state_data: dict, user_data: dict) -> None:
	data_hash = {}
	if state_data.get("video_id_list"):
		data_hash.update({"video_id_list": state_data["video_id_list"]})
	if state_data.get("photo_id_list"):
		data_hash.update({"photo_id_list": state_data["photo_id_list"]})
	
	try:
		psql_cursor.execute(f"""INSERT INTO "Reports table" (text, status, attachments_hashs, chat_id, username) VALUES ('{state_data["text"]}','OPEN','{json.dumps(data_hash)}','{user_data["chat_id"]}','{user_data["tg_username"]}');""")
		logging.debug(f"""Формулировка запроса в SQL:\nINSERT INTO "Reports table" (text, status, attachments_hashs, chat_id, username) VALUES ('{state_data["text"]}','OPEN','{data_hash}','{user_data["chat_id"]}','{user_data["tg_username"]}');""")
	except:
		logging.error(f"Ошибка при отправке запроса SQL")
	
	tmp = (psql_cursor.statusmessage or "").split()
	if len(tmp) > 0:
		rowcount = int(tmp[-1]) if tmp[-1].isdigit() else -1
	else:
		rowcount = -1

	if rowcount == 1:
		psql_cursor.execute(f"""SELECT "ID_rep" FROM "Reports table" WHERE text = '{state_data["text"]}' and attachments_hashs = '{json.dumps(data_hash)}' and chat_id = '{user_data["chat_id"]}' and username = '{user_data["tg_username"]}'""")
		report_number = psql_cursor.fetchone()[0]
		await admin_notification("ticket", report_number)
		return report_number
	else:
		logging.error(f"Ошибка {rowcount} при отправке запроса SQL")	
	return 0

async def create_task(type: str, owner: str, owner_id: int, start_date: str, data, status = "Waiting") -> int:
	logging.debug(f"""Формулировка запроса в SQL:\nINSERT INTO "Tasks table" (type, status, owner, owner_id, start_date, last_change_date, data) VALUES ('{type}','{status}','{owner}','{owner_id}','{start_date}','{start_date}','{json.dumps(data)}')""")
	try:
		psql_cursor.execute(f"""INSERT INTO "Tasks table" (type, status, owner, owner_id, start_date, last_change_date, data) VALUES ('{type}','{status}','{owner}','{owner_id}','{start_date}','{start_date}','{json.dumps(data)}')""")
	except psycopg2.OperationalError as e:
		logging.error(f"Ошибка при отправке запроса SQL {e}")
	
	tmp = (psql_cursor.statusmessage or "").split()
	if len(tmp) > 0:
		rowcount = int(tmp[-1]) if tmp[-1].isdigit() else -1
	else:
		rowcount = -1
	
	if rowcount == 1:
		psql_cursor.execute(f"""SELECT "id" FROM "Tasks table" WHERE type = '{type}' and status = 'Waiting' and owner = '{owner}' and owner_id = '{owner_id}' and start_date = '{start_date}'""")
		task_number = psql_cursor.fetchone()[0]
		return task_number
	else:
		logging.error(f"Ошибка {rowcount} при отправке запроса SQL")
	return

async def admin_notification(type_message: str, work_id: int) -> None:
	psql_cursor.execute(f"""SELECT chat_id FROM "Admins table";""")
	admin_raw_list = psql_cursor.fetchall()
	admin_list = [item[0] for item in admin_raw_list]
	if type_message == "ticket":
		for admin_chat_id in admin_list:
			user_notification(chat_id = admin_chat_id, text = f"Создано новое обращение по пробеме: {work_id}", auto_clean = True)

async def user_notification(chat_id: int, text: str, auto_clean: bool, parse = 'Markdown') -> None:
	delete_notification_button = [[InlineKeyboardButton(text = "Удалить уведомление", callback_data = "delete_notification")]]
	delete_keyboard = InlineKeyboardMarkup(inline_keyboard = delete_notification_button)

	msg = await bot.send_message(chat_id=chat_id, text = text, parse_mode = parse, reply_markup=delete_keyboard)
	if auto_clean:
		tmp_db_redis.lpush("notifications", f"[{chat_id}, {msg.message_id}, {str(datetime.datetime.now())}]")

def batcher(request: str) -> list:
	search_request = request.replace(" ", "", -1)
	result = []
	for temp_group in search_request.split(","):
		if "-" in temp_group:
			start_address = temp_group.split("-")[0]
			final_address = temp_group.split("-")[1]
			if len(start_address) < len(final_address):
				start_address = final_address
				final_address = temp_group.split("-")[0]
			delta = int(start_address.split(".")[-1]) - int(final_address.split(".")[-1])
			if delta < 0:
				for i in range(abs(delta) + 1):
					result.append(f"{start_address.split(".")[0]}.{start_address.split(".")[1]}.{start_address.split(".")[2]}.{int(start_address.split(".")[3]) + i}")
			else:
				for i in range(delta + 1):
					result.append(f"{start_address.split(".")[0]}.{start_address.split(".")[1]}.{start_address.split(".")[2]}.{int(final_address.split(".")[-1]) + int(i)}")
		else:
			result.append(temp_group)
	return list(dict.fromkeys(result))

def alphabet_match(text: str, alphabet=set('abcdefghijklmnopqrstuvwxyz_-.')) -> bool:
	return not alphabet.isdisjoint(text.lower())

# Main commands
@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
	await bot.send_message(chat_id = message.chat.id, text = f"Это *ITCS* _VM portal_ ~bot~", parse_mode = 'Markdown')
	await clean_message(message.chat.id, message.message_id, 3)

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


# Debug commands
@dp.message(Command(commands=["state"]))
async def state_check(message: Message, state: FSMContext):
	current_state = await state.get_state()
	await message.reply(text=f"STATE: {current_state}")

@dp.message(Command(commands=["clear_state"]))
async def state_clear(message: Message, state: FSMContext):
	await state.clear()
	current_state = await state.get_state()
	await message.reply(text=f"STATE cleared: {current_state}")


# Main functions
@dp.callback_query(F.data == "back")
async def back_step(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		current_state = await state.get_state()

		match current_state:
			case "network:menu" | "admin_plane:menu" | "send_report_states:verify_report":
				await main_menu_cal(callback, state)

			case "admin_plane:view_all_tickets":
				await admin_plane_menu(callback, state)

			case "admin_plane:announcement":
				await admin_plane_menu(callback, state)

			case "network:add_ip_form":
				await network_menu(callback, state)

			case "network:internet_access":
				await network_menu(callback, state)

			case "network:internet_access_ip" | "network:internet_access_vm":
				await internet_access(callback, state)

			case "network:internet_resp":
				await internet_access(callback, state)
			
			case "network:status_ip":
				await network_menu(callback, state)

			case "network:status_ip_ip" | "network:status_ip_vm":
				await status_ip(callback, state)

			case _:
				await main_menu_cal(callback, state)

# Network menu
@dp.callback_query(F.data == "network_menu", StateFilter(main_states.menu))
async def network_menu(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		await state.set_state(network.menu)

		keyboard = menu_buttons_build(None, "network_menu")
		
		await bot.edit_message_text(chat_id = callback.from_user.id, message_id = callback.message.message_id, text = "Настройки сети 🌐", reply_markup = keyboard)
		# await bot.send_message(chat_id = callback.from_user.id, text = "Настройки сети 🌐", reply_markup = keyboard)
		# await clean_message(callback.from_user.id, callback.message.message_id, 1)
	else:
		await end_session_notify(callback, state)

@dp.callback_query(F.data == "network_add_ip", StateFilter(network.menu))
async def internet_add_ip(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)
		
		await state.set_state(network.add_ip_form)

		back_button = InlineKeyboardButton(text = "Назад 🔙", callback_data = "back")
		add_ip_button = InlineKeyboardButton(text = "Добавить IP-адрес", callback_data = "add_ip")
		apply_ip_button = InlineKeyboardButton(text = "Подтвердить добавление", callback_data = "apply_ip")

		data = await state.get_data()

		inline_buttons = []

		for i in range(len(data)):
			ip_button = InlineKeyboardButton(text = f"{data[i]["address"]}", callback_data = f"ip_{i}")
			inline_buttons.append([ip_button])

		inline_buttons.append([add_ip_button])
		if len(inline_buttons) > 1:
			inline_buttons.append([apply_ip_button])	
		inline_buttons.append([back_button])
		keyboard = InlineKeyboardMarkup(inline_keyboard = inline_buttons)
		
		await bot.edit_message_text(chat_id = callback.from_user.id, message_id = callback.message.message_id, text = "Заполните необходимые данные", reply_markup=keyboard)
	else:
		await end_session_notify(callback, state)
	return

@dp.callback_query(F.data == "internet_access", StateFilter(network.menu))
async def internet_access(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		await state.set_state(network.internet_access)
		
		keyboard = menu_buttons_build(None, "network_internet_access")
		await bot.edit_message_text(chat_id = callback.from_user.id, message_id = callback.message.message_id, text = "Как будем настраивать? 🔍", reply_markup = keyboard)
		# await bot.send_message(chat_id = callback.from_user.id, text = "Как будем настраивать? 🔍", reply_markup = keyboard)
		# await clean_message(callback.from_user.id, callback.message.message_id, 1)
	else:
		await end_session_notify(callback, state)

@dp.callback_query(F.data == "internet_vm", StateFilter(network.internet_access))
async def internet_vm(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		await state.set_state(network.internet_access_vm)

		keyboard = menu_buttons_build(None, "back_only")
		await bot.edit_message_text(chat_id = callback.from_user.id, message_id = callback.message.message_id,
							  text = "Введите название виртуальной машины 💻",
							  reply_markup = keyboard)
		# await bot.send_message(chat_id = callback.from_user.id, text = "Введите название виртуальной машины 💻", reply_markup = keyboard)
		# await clean_message(callback.from_user.id, callback.message.message_id, 1)
	else:
		await end_session_notify(callback, state)

@dp.callback_query(F.data == "internet_ip", StateFilter(network.internet_access))
async def internet_ip(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		await state.set_state(network.internet_access_ip)

		keyboard = menu_buttons_build(None, "back_only")

		await bot.edit_message_text(chat_id = callback.from_user.id, message_id = callback.message.message_id,
							  text = "Введите один или несколько искомых IP-адресов (без указания маски)\n\n_Несколько адресов можно указать через запятую или диапазон (для последнего октета)_\nНапример: 10.1.102.4, 10.1.102.47 - 54",
							  reply_markup = keyboard)
		# await bot.send_message(chat_id = callback.from_user.id, text = "Введите один или несколько искомых IP-адресов (без указания маски)\n\n_Несколько адресов можно указать через запятую или диапазон (для последнего октета)_\nНапример: 10.1.102.4, 10.1.102.47 - 54",parse_mode = 'Markdown', reply_markup = keyboard)
		# await clean_message(callback.from_user.id, callback.message.message_id, 1)
	else:
		await end_session_notify(callback, state)

@dp.message(F.content_type.in_({'text'}), StateFilter(network.internet_access_ip, network.internet_access_vm))
async def internet_resp(message: Message, state: FSMContext) -> None:
	if check_session(session_db_redis, message.chat.username):
		update_session(session_db_redis, message.chat.username)

		current_state = await state.get_state()
		await state.set_state(network.internet_resp)

		status_msg = await bot.send_message(chat_id = message.chat.id, text = "_Запрос в базу данных..._", parse_mode='markdown')

		keyboard_back = menu_buttons_build(None, "back_only")

		operational_data = []

		back_button = InlineKeyboardButton(text = "Назад 🔙", callback_data = "back")

		if current_state == "network:internet_access_ip":
			search_request = batcher(message.text)
			for address in search_request:
				net_data = get_ip_info(address)
				if net_data:
					if net_data == "Error":
						await bot.send_message(chat_id = message.chat.id, text = "Ошибка связи с Netbox", reply_markup = keyboard_back)
						await clean_message(message.chat.id, message.message_id, 2)
						try:
							await bot.delete_message(chat_id = message.chat.id, message_id=status_msg.message_id)
						except:
							pass
						return
					operational_data.append({"address": net_data["address"], "role": net_data["role"],
							  "machine_name": net_data["custom_fields"]["Machine_Name"].split(" | ") if net_data["custom_fields"]["Machine_Name"] else "None"})
				else:
					await user_notification(chat_id = message.chat.id, text = f"IP {address} не найден", auto_clean = False, parse=None)
			
			await bot.edit_message_text(chat_id = message.chat.id, message_id=status_msg.message_id, text = "_Уточнение наличия выхода в интернет..._", parse_mode='markdown')
			
			internet_flags = await get_ip_net_info(search_request)
			if internet_flags == "Error":
				await bot.send_message(chat_id = message.chat.id, text = "Ошибка связи с МСЭ", reply_markup = keyboard_back)
				await clean_message(message.chat.id, message.message_id, 2)
				try:
					await bot.delete_message(chat_id = message.chat.id, message_id=status_msg.message_id)
				except:
					pass
				return
			
			await bot.edit_message_text(chat_id = message.chat.id, message_id=status_msg.message_id, text = "_Подготовка данных..._",parse_mode='markdown')
			
			inline_buttons = []
			for i in range(len(operational_data)):
				operational_data[i].update({"internet": internet_flags[i]})
				internet_flag_access = InlineKeyboardButton(text = f"{'VIP:' if operational_data[i]["role"] == 'vip' else ''} {operational_data[i]["address"]} {'✅' if operational_data[i]["internet"] else '❌'}", callback_data=f"internet_flag_{i}")
				inline_buttons.append([internet_flag_access])

			inline_buttons.append([back_button])

			keyboard = InlineKeyboardMarkup(inline_keyboard = inline_buttons)
			
			data_message = await bot.send_message(chat_id = message.chat.id, text = "Доступ в интернет у следующих адресов:\nНажмите на IP-адрес для изменения доступа на противоположный", reply_markup=keyboard)

			result_operational_data = {"start_data": operational_data, "new_data": operational_data, "msg_id": data_message.message_id}

			await state.set_data(result_operational_data)
			
			await bot.delete_message(chat_id = message.chat.id, message_id=status_msg.message_id)
		else:
			vm_data = get_vm_info(message.text)
			if len(vm_data) == 0:
				await bot.send_message(chat_id=message.from_user.id, text = f"Информация о виртуальной машине {message.text} не найдена", reply_markup=keyboard_back)
				await bot.delete_message(chat_id = message.chat.id, message_id=status_msg.message_id)
				await clean_message(message.chat.id, message.message_id, 2)
				return
			elif len(vm_data) == 1:
				operational_data = []
				for address in vm_data[0]["networks"]:
					operational_data.append({"address": f'VIP: {address["address"]}' if address["role"] == "vip" else address["address"],
							  "machine_name": address["Machine_Name"]})
				
				await bot.edit_message_text(chat_id = message.chat.id, message_id=status_msg.message_id, text = "_Уточнение наличия выхода в интернет..._", parse_mode='markdown')
				
				internet_flags = []
				for ip in vm_data[0]["networks"]:
					internet_flags.append(ip["address"].split("/")[0])
				internet_flags = await get_ip_net_info(internet_flags)
				if internet_flags == "Error":
					await bot.send_message(chat_id = message.chat.id, text = "Ошибка связи с МСЭ", reply_markup = keyboard_back)
					await clean_message(message.chat.id, message.message_id, 2)
					try:
						await bot.delete_message(chat_id = message.chat.id, message_id=status_msg.message_id)
					except:
						pass
					return
				
				await bot.edit_message_text(chat_id = message.chat.id, message_id=status_msg.message_id, text = "_Подготовка данных..._",parse_mode='markdown')
				
				inline_buttons = []

				for i in range(len(operational_data)):
					operational_data[i].update({"internet": internet_flags[i]})
					internet_flag_access = InlineKeyboardButton(text = f"{operational_data[i]["address"]} {'✅' if operational_data[i]["internet"] else '❌'}", callback_data=f"internet_flag_{i}")
					inline_buttons.append([internet_flag_access])
				
				inline_buttons.append([back_button])
				keyboard = InlineKeyboardMarkup(inline_keyboard = inline_buttons)

				data_message = await bot.send_message(chat_id = message.chat.id, text = f"Доступ в интернет для {vm_data[0]["networks"][0]["Machine_Name"][0]}\nНажмите на IP-адрес для изменения доступа на противоположный", reply_markup=keyboard)

				result_operational_data = {"start_data": operational_data, "new_data": operational_data, "msg_id": data_message.message_id}

				await state.set_data(result_operational_data)
				await bot.delete_message(chat_id = message.chat.id, message_id=status_msg.message_id)
			else:
				inline_buttons = []
				machines_list = []
				for i in range(len(vm_data)):
					vm_search_button = InlineKeyboardButton(text = f"{vm_data[i]["Machine_Name"]}", callback_data=f"internet_search_vm_{i}")
					inline_buttons.append([vm_search_button])
					machines_list.append(vm_data[i]["Machine_Name"])
				inline_buttons.append([back_button])
				keyboard = InlineKeyboardMarkup(inline_keyboard = inline_buttons)

				await state.set_data(machines_list)

				await bot.send_message(chat_id=message.from_user.id, text = "Найденные варианты: 📋", reply_markup=keyboard)
				await bot.delete_message(chat_id = message.chat.id, message_id=status_msg.message_id)
			

		await clean_message(message.chat.id, message.message_id, 2)
	else:
		await end_session_notify(message, state)

@dp.callback_query(F.data.startswith("internet_search_vm_"), StateFilter(network.internet_resp))
async def internet_resp_cal(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		status_msg = await bot.send_message(chat_id = callback.from_user.id, text = "_Запрос в базу данных..._", parse_mode='markdown')

		back_button = InlineKeyboardButton(text = "Назад 🔙", callback_data = "back")
		keyboard_back = menu_buttons_build(None, "back_only")

		search_index = int(callback.data.split("_", maxsplit=3)[3])
		state_data = await state.get_data()
		search_request = state_data[search_index]
		vm_data = get_vm_info(search_request)

		operational_data = []

		for address in vm_data[0]["networks"]:
			operational_data.append({"address": address["address"],
							"role": address["role"],
							"machine_name": address["Machine_Name"]})
			
		await bot.edit_message_text(chat_id = callback.from_user.id, message_id=status_msg.message_id, text = "_Уточнение наличия выхода в интернет..._", parse_mode='markdown')
		internet_flags = []
		for ip in vm_data[0]["networks"]:
			internet_flags.append(ip["address"].split("/")[0])
		internet_flags = await get_ip_net_info(internet_flags)
		if internet_flags == "Error":
			await bot.send_message(chat_id = callback.from_user.id, text = "Ошибка связи с МСЭ", reply_markup = keyboard_back)
			await clean_message(callback.from_user.id, callback.message.message_id, 2)
			try:
				await bot.delete_message(chat_id = callback.from_user.id, message_id=status_msg.message_id)
			except:
				pass
			return

		await bot.edit_message_text(chat_id = callback.from_user.id, message_id=status_msg.message_id, text = "_Подготовка данных..._",parse_mode='markdown')
		inline_buttons = []
		for i in range(len(operational_data)):
			operational_data[i].update({"internet": internet_flags[i]})
			internet_flag_access = InlineKeyboardButton(text = f"{'VIP:' if operational_data[i]["role"] == 'vip' else ''} {operational_data[i]["address"]} {'✅' if operational_data[i]["internet"] else '❌'}", callback_data=f"internet_flag_{i}")
			inline_buttons.append([internet_flag_access])

		inline_buttons.append([back_button])
		keyboard = InlineKeyboardMarkup(inline_keyboard = inline_buttons)
		data_message = await bot.send_message(chat_id = callback.from_user.id, text = f"Доступ в интернет для {search_request}", reply_markup=keyboard)
		result_operational_data = {"start_data": operational_data, "new_data": operational_data, "msg_id": data_message.message_id}

		await state.set_data(result_operational_data)			
		await bot.delete_message(chat_id = callback.from_user.id, message_id=status_msg.message_id)
		await clean_message(callback.from_user.id, callback.message.message_id, 1)
	else:
		await end_session_notify(callback, state)

@dp.callback_query(F.data.startswith("internet_flag_"), StateFilter(network.internet_resp))
async def internet_change_flag(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		internet_flag_index = int(callback.data.split("_")[2])
		operational_data = await state.get_data()
		if operational_data["new_data"][internet_flag_index]["internet"]:
			operational_data["new_data"][internet_flag_index]["internet"] = False
		else:
			operational_data["new_data"][internet_flag_index]["internet"] = True

		await state.set_data(operational_data)
		
		back_button = InlineKeyboardButton(text = "Назад 🔙", callback_data = "back")
		internet_apply = InlineKeyboardButton(text = f"Подтвердить", callback_data="internet_apply")
		inline_buttons = []

		for i in range(len(operational_data["new_data"])):
			internet_flag_access = InlineKeyboardButton(text = f"{'VIP:' if operational_data["new_data"][i]["role"] == 'vip' else ''} {operational_data["new_data"][i]["address"]} {'✅' if operational_data["new_data"][i]["internet"] else '❌'}", callback_data=f"internet_flag_{i}")
			inline_buttons.append([internet_flag_access])

		inline_buttons.append([internet_apply])
		inline_buttons.append([back_button])

		keyboard = InlineKeyboardMarkup(inline_keyboard = inline_buttons)

		await bot.edit_message_reply_markup(chat_id = callback.from_user.id, message_id=operational_data["msg_id"], reply_markup=keyboard)

	else:
		await end_session_notify(callback, state)

@dp.callback_query(F.data == "internet_apply", StateFilter(network.internet_resp))
async def internet_change_task(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		operational_data = await state.get_data()

		delta = []

		for i in range(len(operational_data["start_data"])):
			if operational_data["start_data"][i] != operational_data["new_data"][i]:
				delta.append(operational_data["new_data"][i])
			
		if len(delta) == 0:
			msg = "Отсутствие изменений. Действия не будут выполнены"
		else:
			new_task_id = await create_task(type = "internet_access", owner = callback.from_user.username, owner_id = callback.from_user.id, start_date = datetime.datetime.now(), data = delta)
			msg = f"Создана задача с номером: _{new_task_id}_\nИзменений: _{len(delta)}_\n\n*Примерное время выполнения 2 минуты*"
		
		await user_notification(chat_id = callback.from_user.id, text = msg, auto_clean = True)
		await clean_message(callback.from_user.id, callback.message.message_id, 1)
		await main_menu_cal(callback, state)

	else:
		await end_session_notify(callback, state)

@dp.callback_query(F.data == "status_ip", StateFilter(network.menu))
async def status_ip(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		await state.set_state(network.status_ip)

		keyboard = menu_buttons_build(None, "network_menu_status")

		await bot.edit_message_text(chat_id = callback.from_user.id, message_id = callback.message.message_id,
							  text = "Что узнаем? 🤔",
							  reply_markup = keyboard)
		# await bot.send_message(chat_id = callback.from_user.id, text = "Что узнаем? 🤔", reply_markup=keyboard)
		# await clean_message(callback.from_user.id, callback.message.message_id, 1)
	else:
		await end_session_notify(callback, state)

@dp.callback_query(F.data == "status_ip_ip", StateFilter(network.status_ip))
async def status_ip_ip(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		await state.set_state(network.status_ip_ip)

		keyboard = menu_buttons_build(None, "back_only")

		await bot.edit_message_text(chat_id = callback.from_user.id, message_id = callback.message.message_id,
							  text = "Введите запрос для поиска IP-адреса\n\n_Несколько адресов можно указать через запятую или диапазон (для последнего октета)_\nНапример: 10.1.102.4, 10.1.102.47 - 54",
							  parse_mode = 'Markdown',
							  reply_markup = keyboard)
		# await bot.send_message(chat_id = callback.from_user.id, text = "Введите запрос для поиска IP-адреса\n\n_Несколько адресов можно указать через запятую или диапазон (для последнего октета)_\nНапример: 10.1.102.4, 10.1.102.47 - 54", parse_mode = 'Markdown', reply_markup=keyboard)
		# await clean_message(callback.from_user.id, callback.message.message_id, 1)
	else:
		await end_session_notify(callback, state)

@dp.callback_query(F.data == "status_ip_vm", StateFilter(network.status_ip))
async def status_ip_vm(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		await state.set_state(network.status_ip_vm)

		keyboard = menu_buttons_build(None, "back_only")

		await bot.edit_message_text(chat_id = callback.from_user.id, message_id = callback.message.message_id,
							  text = "Введите название виртуальной машины или его часть",
							  reply_markup = keyboard)
		# await bot.send_message(chat_id = callback.from_user.id, text = "Введите название виртуальной машины или его часть", reply_markup=keyboard)
		# await clean_message(callback.from_user.id, callback.message.message_id, 1)
	else:
		await end_session_notify(callback, state)

@dp.message(F.content_type.in_({'text'}), StateFilter(network.status_ip_ip, network.status_ip_vm))
async def status_ip_resp(message: Message, state: FSMContext) -> None:
	if check_session(session_db_redis, message.chat.username):
		update_session(session_db_redis, message.chat.username)
		
		current_state = await state.get_state()
		await state.set_state(network.status_ip)
		
		keyboard = menu_buttons_build(None, "network_menu_status")

		status_msg = await bot.send_message(chat_id = message.chat.id, text = "_Запрос в базу данных..._", parse_mode='markdown')

		operational_data = []
		ip_data = []
		inet_matrix = []

		if current_state == "network:status_ip_ip":
			raw_ip_data = batcher(message.text)
			for ip in raw_ip_data:
				net_data = get_ip_info(ip)
				if net_data:
					if net_data == "Error":
						await user_notification(chat_id = message.chat.id, text = f"Ошибка связи с netbox", auto_clean = False, parse=None)
						await bot.send_message(chat_id = message.chat.id, text = "Что узнаем? 🤔", reply_markup = keyboard)
						await clean_message(message.chat.id, message.message_id, 2)
						try:
							await bot.delete_message(chat_id = message.chat.id, message_id=status_msg.message_id)
						except:
							pass
						return
					
					ip_data.append(net_data)
					inet_matrix.append(ip)
				else:
					ip_data.append(f"IP: {ip}\nСтатус: Available")

			await bot.edit_message_text(chat_id = message.chat.id, message_id=status_msg.message_id, text = "_Уточнение наличия выхода в интернет..._",parse_mode='markdown')
			inet_matrix = await get_ip_net_info(inet_matrix)
			if inet_matrix == "Error":
				await user_notification(chat_id = message.chat.id, text = f"Ошибка связи с МСЭ", auto_clean = False, parse=None)
				await bot.send_message(chat_id = message.chat.id, text = "Что узнаем? 🤔", reply_markup = keyboard)
				await clean_message(message.chat.id, message.message_id, 2)
				try:
					await bot.delete_message(chat_id = message.chat.id, message_id=status_msg.message_id)
				except:
					pass
				return

			await bot.edit_message_text(chat_id = message.chat.id, message_id=status_msg.message_id, text = "_Подготовка данных..._",parse_mode='markdown')

			count_avail = 0

			for ip in ip_data:
				if type(ip) == dict:
					msg = f"""IP: {ip["address"]}
Роль: {ip["role"]}
Статус: {ip["status"]}
Тип системы: {ip["custom_fields"]["Implementation_type"]}"""
					
					ip_index = ip_data.index(ip)

					if ip["custom_fields"]["Machine_Name"]:
						temp = ip["custom_fields"]["Machine_Name"].split(" | ")
						for vm_count in range(len(temp)):
							msg += f"\n{ip["custom_fields"]["Implementation_type"]} {vm_count + 1}: {temp[vm_count]}"
						if ip["tenant"]:
							msg += f"\nВладелец: {ip["tenant"]["name"]}\nДоступ в интернет: {'✅' if inet_matrix[ip_index - count_avail] else '❌'}"
						else:
							msg += f"\nВладелец: None\nДоступ в интернет: {'✅' if inet_matrix[ip_index - count_avail] else '❌'}"
					elif len(ip["description"]) != 0:
						msg += f"\n{net_data["custom_fields"]["Implementation_type"]}: {ip["description"]}"
					else:
						msg += f"\n{ip["custom_fields"]["Implementation_type"]}: IP не привязан, либо зарезервирован 😥"

					operational_data.append(msg)
				else:
					count_avail += 1
					operational_data.append(ip)
					
			msg = ""
			for result_data in operational_data:
				msg += result_data +"\n\n"
				
			if len(msg) > 4096:
				for x in range(0, len(msg), 4096):
					await user_notification(chat_id = message.chat.id, text = msg[x:x + 4096], auto_clean = False, parse=None)
			else:
				await user_notification(chat_id = message.chat.id, text = msg, auto_clean = False, parse=None)

			await bot.send_message(chat_id = message.chat.id, text = "Что узнаем? 🤔", reply_markup = keyboard)
			try:
				await bot.delete_message(chat_id = message.chat.id, message_id=status_msg.message_id)
			except:
				pass
		else:
			vm_data = get_vm_info(message.text)
			logging.debug(f"Ответ netbox {vm_data}")
			if len(vm_data) == 0:
				msg = "Информация о виртуальной машине не найдена"
				await bot.send_message(chat_id = message.chat.id, text = msg, reply_markup = keyboard)

				try:
					await bot.delete_message(chat_id = message.chat.id, message_id=status_msg.message_id)
				except:
					pass

			else:
				msg = ""
				
				await bot.edit_message_text(chat_id = message.chat.id, message_id=status_msg.message_id, text = "_Уточнение наличия выхода в интернет..._",parse_mode='markdown')
				
				ip_inet_matrix = []
				for vm_name in vm_data:
					for ip in vm_name["networks"]:
						ip_inet_matrix.append(ip["address"].split("/")[0])

				ip_inet_matrix = await get_ip_net_info(ip_inet_matrix)
				if ip_inet_matrix == "Error":
					await user_notification(chat_id = message.chat.id, text = f"Ошибка связи с МСЭ", auto_clean = False, parse=None)
					await bot.send_message(chat_id = message.chat.id, text = "Что узнаем? 🤔", reply_markup = keyboard)
					await clean_message(message.chat.id, message.message_id, 2)
					try:
						await bot.delete_message(chat_id = message.chat.id, message_id=status_msg.message_id)
					except:
						pass
					return

				for vm_name in vm_data:
					msg += f'\n{vm_name["Machine_Name"]}\n'
					for ip in vm_name["networks"]:
						msg += f"""---------------
IP: {ip["address"]}
Тип: {ip["Implementation_type"]}
Роль: {ip["role"]}
Статус: {ip["status"]}
Владелец: {ip["tenant"]}
"""
						for vm_cluster_count in range(len(ip["Machine_Name"])):
							msg += f"Нода {vm_cluster_count + 1}: {ip["Machine_Name"][vm_cluster_count]}\n"
						msg += f"Доступ в интернет: {'✅' if ip_inet_matrix[vm_name["networks"].index(ip)] else '❌'}\n"
				
				await bot.edit_message_text(chat_id = message.chat.id, message_id=status_msg.message_id, text = "_Подготовка данных..._",parse_mode='markdown')

				if len(msg) > 4096:
					for x in range(0, len(msg), 4096):
						await user_notification(chat_id = message.chat.id, text = msg[x:x + 4096], auto_clean = False, parse=None)
				else:
					await user_notification(chat_id = message.chat.id, text = msg, auto_clean = False, parse=None)
				
				await bot.send_message(chat_id = message.chat.id, text = "Что узнаем? 🤔", reply_markup = keyboard)

				try:
					await bot.delete_message(chat_id = message.chat.id, message_id=status_msg.message_id)
				except:
					pass

		await clean_message(message.chat.id, message.message_id, 2)
	else:
		await end_session_notify(message, state)

# Admin menu
@dp.callback_query(F.data == "admin_plane_menu", StateFilter(main_states.menu))
async def admin_plane_menu(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		await state.set_state(admin_plane.menu)

		keyboard = menu_buttons_build("Admin", "admin_plane")

		await bot.edit_message_text(chat_id =callback.from_user.id, message_id = callback.message.message_id, text = "Панель Администратора👑", reply_markup = keyboard)
		# await bot.send_message(chat_id = callback.from_user.id, text = "Панель Администратора👑", reply_markup = keyboard)
		# await clean_message(callback.from_user.id, callback.message.message_id, 1)
	else:
		await end_session_notify(callback, state)

@dp.callback_query(F.data == "announcement", StateFilter(admin_plane.menu))
async def announcement_text(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		await state.set_state(admin_plane.announcement)

		keyboard = menu_buttons_build(None, 'back_only')

		await bot.edit_message_text(chat_id=callback.from_user.id,message_id=callback.message.message_id , text = "Введите текст объявления.\n\n*Ограничение 4096 символов*", parse_mode='Markdown', reply_markup=keyboard)
	else:
		await end_session_notify(callback, state)

@dp.message(F.content_type.in_({'text'}), StateFilter(admin_plane.announcement))
async def announcement_text_preview(message: Message, state: FSMContext) -> None:
	if check_session(session_db_redis, message.chat.username):
		update_session(session_db_redis, message.chat.username)

		keyboard = menu_buttons_build(None, "announcement_preview")

		await state.set_data(str(message.text))

		await bot.edit_message_text(chat_id = message.from_user.id, message_id=message.message_id - 1, text = str(message.text), reply_markup=keyboard)
		await clean_message(message.chat.id, message.message_id, 1)
	else:
		await end_session_notify(message, state)

@dp.callback_query(F.data == "announcement_apply", StateFilter(admin_plane.announcement))
async def announcement_text_apply(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		text = await state.get_data()
		psql_cursor.execute(f"""SELECT * FROM "Users table";""")
		users = psql_cursor.fetchall()
		if users:
			for user in users:
				await user_notification(chat_id=user[1], text = text, auto_clean=False, parse = None)
		else:
			logging.error(f"Ошибка при рассылке уведомления пользователям")
		await main_menu_cal(callback, state)
	else:
		await end_session_notify(callback, state)

@dp.callback_query(F.data.startswith("all_tickets_"), StateFilter(admin_plane.menu, admin_plane.view_all_tickets))
async def all_tickets(callback: CallbackQuery, state: FSMContext):
	state_ticket_action = callback.data.split("_")[2]
	if state_ticket_action == "0":
		# Выгрузка первого тикета
		psql_cursor.execute("""SELECT * FROM "Reports table" LIMIT 1""")
		result = psql_cursor.fetchone()
		if result:
			ticket_text = result[0]
			ticket_state = result[1]
			ticket_attachments = result[2]
			ticket_owner_chat_id = result[3]
			ticket_owner_username = result[4]
			ticket_number = result[5]
			
			album_builder = None #ADD

			await state.set_state(admin_plane.view_all_tickets)

			keyboard = menu_buttons_build(None, "all_tickets")

			await state.set_data({"ticket_number": ticket_number})

			await bot.edit_message_text(chat_id = callback.from_user.id, message_id=callback.message.message_id,
							   text = f"Тикет: {ticket_number}\nСостояние: *{ticket_state}*\nОтправитель: @{ticket_owner_username}\n\n_{ticket_text}_",
							   parse_mode = "Markdown", reply_markup = keyboard)
			# await bot.send_message(chat_id = callback.from_user.id,
			# 		text = f"Тикет: {ticket_number}\nСостояние: *{ticket_state}*\nОтправитель: @{ticket_owner_username}\n\n_{ticket_text}_",
			# 		parse_mode = "Markdown", reply_markup = keyboard)
			# await clean_message(callback.from_user.id, callback.message.message_id, 12)
		
		else:
			keyboard = menu_buttons_build(None, "back_only")
			await bot.send_message(chat_id = callback.from_user.id, text = f"Тикеты не обнаружены", reply_markup = keyboard)
	
	elif state_ticket_action == "slide-left":
		print("decr")
	
	elif state_ticket_action == "slide-right":
		state_ticket_number = await state.get_data()
		print(state_ticket_number["ticket_number"])

# Main menu
@dp.message(Command(commands=["menu"]))
async def main_menu(message: Message, state: FSMContext) -> None:
		
	current_state = await state.get_state()
	
	if current_state and check_session(session_db_redis, message.chat.username):
		update_session(session_db_redis, message.chat.username)
		await state.set_state(main_states.menu)
		user_data = load_user_data(session_db_redis, message.chat.username, ["ldap_fullname", "access_level"])
		await bot.send_message(chat_id = message.chat.id, text = f"Добро пожаловать *{user_data["ldap_fullname"]}*!\nУровень доступа: _{user_data["access_level"]}_", parse_mode = 'Markdown', reply_markup = menu_buttons_build(user_data["access_level"], "main_menu"))
	else:
		await end_session_notify(message, state)
	
	await clean_message(message.chat.id, message.message_id, 3)

async def main_menu_cal(callback: CallbackQuery, state: FSMContext) -> None:	
	update_session(session_db_redis, callback.from_user.username)

	await state.clear()
	await state.set_state(main_states.menu)
	
	user_data = load_user_data(session_db_redis, callback.from_user.username, ["ldap_fullname", "access_level"])
	await bot.send_message(chat_id = callback.from_user.id,
						text = f"Добро пожаловать *{user_data["ldap_fullname"]}*!\nУровень доступа: _{user_data["access_level"]}_",
						parse_mode = 'Markdown',
						reply_markup = menu_buttons_build(user_data["access_level"], "main_menu"))
	
	await clean_message(callback.from_user.id, callback.message.message_id, 12)

# Report menu
@dp.callback_query(F.data == 'send_report', StateFilter(send_report_states.verify_report))
async def send_report_notify(callback: CallbackQuery, state: FSMContext) -> None:
	update_session(session_db_redis, callback.from_user.username)

	state_data = await state.get_data()
	await state.clear()
	await state.set_state(main_states.menu)

	user_data = load_user_data(session_db_redis, callback.from_user.username, ["chat_id", "tg_username", "ldap_fullname", "access_level"])
	report_num = await send_report(state_data, user_data)

	logging.debug(f"Пользователь {callback.from_user.username} отправил репорт. State={await state.get_state()}. State_data={state_data}")
	await user_notification(chat_id = callback.from_user.id, text = f"Ваш запрос успешно отправлен!\nНомер запроса: *{report_num}*", auto_clean = True)

	await main_menu_cal(callback, state)


@dp.callback_query(F.data == 'session_end', StateFilter(main_states.menu))
async def end_user_session(callback: CallbackQuery, state: FSMContext) -> None:
	username = callback.from_user.username

	if exit_session(session_db_redis, username):
		login_button = [KeyboardButton(text = f"Авторизироваться как {username}", web_app = webapp)]
		login_keyboard = ReplyKeyboardMarkup(keyboard = [login_button], resize_keyboard=True)

		await bot.send_message(chat_id = callback.from_user.id, text = "Сессия успешно завершена. Пожалуйста пройди авторизацию", reply_markup = login_keyboard)
		await state.clear()

		logging.debug(f"Сессия пользователя {username} успешно завершена")
	else:
		await bot.send_message(chat_id = callback.from_user.id, text = "Ошибка при закрытии сессии😱\nПожалуйста, обратитесь к администратору")
		
		logging.error(f"Ошибка при ручном завершении сессии пользователем {username}")
	
	await clean_message(callback.from_user.id, callback.message.message_id, 1)


@dp.callback_query(F.data == 'report_menu', StateFilter(main_states.menu, send_report_states.verify_report))
async def text_report(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)
		
		await state.set_state(send_report_states.print_text_report)

		state_data = await state.get_data()
		state_data_text = state_data.get("text")

		logging.debug(f"Пользователь {callback.from_user.username} перешел в report_menu. State={await state.get_state()}. State_data={state_data}")

		keyboard = menu_buttons_build(None, "back_only")

		await bot.send_message(chat_id = callback.from_user.id, text = (f"Пожалуйста опишите свою проблему\nВаше предыдущее сообщение:\n_{state_data["text"]}_" if state_data_text else "Пожалуйста опишите свою проблему"), parse_mode = 'Markdown', reply_markup = keyboard)
		await clean_message(callback.from_user.id, callback.message.message_id, 1)
	else:
		await end_session_notify(callback, state)


@dp.message(F.content_type.in_({'text'}), StateFilter(send_report_states.print_text_report))
async def report_preview(message: Message, state: FSMContext) -> None:
	if check_session(session_db_redis, message.chat.username):
		update_session(session_db_redis, message.chat.username)
		
		await state.set_state(send_report_states.verify_report)
		if message.text:
			await state.update_data(text=message.text)

		state_data = await state.get_data()

		logging.debug(f"Пользователь {message.chat.username} перешел в report_preview. State={await state.get_state()}. State_data={state_data}")

		keyboard = menu_buttons_build(None, "report_preview")

		await bot.send_message(chat_id = message.chat.id, text = state_data["text"], reply_markup = keyboard)
		await clean_message(message.chat.id, message.message_id, 2)
	else:
		await end_session_notify(message, state)


@dp.callback_query(F.data == 'exit_changes', StateFilter(send_report_states.media_verify))
async def report_preview_cal(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		await state.set_state(send_report_states.verify_report)
		
		state_data = await state.get_data()

		logging.debug(f"Пользователь {callback.from_user.username} перешел в report_preview_cal. State={await state.get_state()}. State_data={state_data}")

		album_builder = MediaGroupBuilder()

		if state_data.get('photo_id_list'):
			for photo in state_data["photo_id_list"]:
				album_builder.add_photo(media=photo)
		if state_data.get('video_id_list'):
			for video in state_data['video_id_list']:
				album_builder.add_video(media=video)
		
		try:
			await bot.send_media_group(chat_id = callback.from_user.id, media = album_builder.build())
		except:
			pass

		keyboard = menu_buttons_build(None, "report_preview")

		await bot.send_message(chat_id = callback.from_user.id, text = state_data["text"], parse_mode = 'Markdown', reply_markup = keyboard)
		await clean_message(callback.from_user.id, callback.message.message_id, 12)
	else:
		await end_session_notify(callback, state)


@dp.callback_query(F.data == 'change_picture', StateFilter(send_report_states.verify_report))
async def media_verify(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		await state.set_state(send_report_states.media_verify)
		state_data = await state.get_data()

		logging.debug(f"Пользователь {callback.from_user.username} перешел в media_verify. State={await state.get_state()}. State_data={state_data}")

		add_media_button = InlineKeyboardButton(text = "Добавить вложение➕", callback_data = "add_media")
		delete_media_button = InlineKeyboardButton(text = "Удалить вложение➖", callback_data = "delete_media")
		exit_changes_button = InlineKeyboardButton(text = "Закончить редактирование вложений🚪", callback_data = "exit_changes")

		media_verify_finish_list = [[add_media_button], [delete_media_button], [exit_changes_button]]
		keyboard = InlineKeyboardMarkup(inline_keyboard = media_verify_finish_list)

		await bot.send_message(chat_id = callback.from_user.id, text = "Прикрепленные медиа:", parse_mode = 'Markdown', reply_markup = keyboard)
		await clean_message(callback.from_user.id, callback.message.message_id, 1)
	else:
		await end_session_notify(callback, state)


@dp.message(F.content_type.in_({'photo', 'video', 'text'}), StateFilter(send_report_states.media_add, send_report_states.media_del))
async def media_verify_msg(message: Message, state: FSMContext) -> None:
	if check_session(session_db_redis, message.chat.username):
		update_session(session_db_redis, message.chat.username)

		await state.set_state(send_report_states.media_verify)

		state_data = await state.get_data()

		if message.text:
			if state_data.get('photo_id_list') and state_data.get('video_id_list'):
				photo_id_list = state_data['photo_id_list']
				video_id_list = state_data['video_id_list']

				if int(message.text) <= (len(photo_id_list) + len(video_id_list)):
					if int(message.text) < len(photo_id_list):
						del photo_id_list[int(message.text) - 1]
					else:
						del video_id_list[int(message.text) - len(photo_id_list) - 1]
					
					await state.update_data(photo_id_list = photo_id_list)
					await state.update_data(video_id_list = video_id_list)

			elif state_data.get('photo_id_list'):
				photo_id_list = state_data['photo_id_list']
				if int(message.text) <= len(photo_id_list):
					del photo_id_list[int(message.text) - 1]
				
				await state.update_data(photo_id_list = photo_id_list)

			else:
				video_id_list = state_data['video_id_list']
				if int(message.text) <= len(video_id_list):
					del video_id_list[int(message.text) - 1]

				await state.update_data(video_id_list = video_id_list)

		else:
			if message.photo:
				if state_data.get('photo_id_list'):
					photo_id_list = state_data['photo_id_list']
					photo_id_list.append(message.photo[0].file_id)
					await state.update_data(photo_id_list = photo_id_list)
				else:
					await state.update_data(photo_id_list = [message.photo[0].file_id])
			if message.video:
				if state_data.get('video_id_list'):
					video_id_list = state_data['video_id_list']
					video_id_list.append(message.video.file_id)
					await state.update_data(video_id_list = video_id_list)
				else:
					await state.update_data(video_id_list = [message.video.file_id])
		state_data = await state.get_data()

		logging.debug(f"Пользователь {message.chat.username} перешел в media_verify_msg. State={await state.get_state()}. State_data={state_data}")

		album_builder = MediaGroupBuilder()

		if state_data.get('photo_id_list'):
			for photo in state_data["photo_id_list"]:
				album_builder.add_photo(media=photo)
		if state_data.get('video_id_list'):
			for video in state_data['video_id_list']:
				album_builder.add_video(media=video)

		add_media_button = InlineKeyboardButton(text = "Добавить вложение➕", callback_data = "add_media")
		delete_media_button = InlineKeyboardButton(text = "Удалить вложение➖", callback_data = "delete_media")
		exit_changes_button = InlineKeyboardButton(text = "Закончить редактирование вложений🚪", callback_data = "exit_changes")

		media_verify_finish_list = [[add_media_button], [delete_media_button], [exit_changes_button]]
		keyboard = InlineKeyboardMarkup(inline_keyboard = media_verify_finish_list)

		
		
		try:
			await bot.send_media_group(chat_id = message.chat.id, media = album_builder.build())
		except:
			pass

		await bot.send_message(chat_id = message.chat.id, text = "Прикрепленные медиа:", parse_mode = 'Markdown', reply_markup = keyboard)
		await clean_message(message.chat.id, message.message_id, 12)
	else:
		await end_session_notify(message, state)


@dp.callback_query(F.data == 'delete_media', StateFilter(send_report_states.media_verify))
async def media_del(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		

		await state.set_state(send_report_states.media_del)

		state_data = await state.get_data()

		logging.debug(f"Пользователь {callback.from_user.username} перешел в media_del. State={await state.get_state()}. State_data={state_data}")

		await bot.send_message(chat_id = callback.from_user.id, text = "Укажите номер вложения которое нужно удалить")
		await clean_message(callback.from_user.id, callback.message.message_id, 1)
	else:
		await end_session_notify(callback, state)


@dp.callback_query(F.data == 'add_media', StateFilter(send_report_states.media_verify))
async def media_add(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		await state.set_state(send_report_states.media_add)

		state_data = await state.get_data()

		logging.debug(f"Пользователь {callback.from_user.username} перешел в media_add. State={await state.get_state()}. State_data={state_data}")

		await bot.send_message(chat_id = callback.from_user.id, text = "Отправьте пожалуйста одно фото или видео вложение с использованием сжатия", parse_mode = 'Markdown')
		await clean_message(callback.from_user.id, callback.message.message_id, 12)
	else:
		await end_session_notify(callback, state)


@dp.callback_query(F.data == "last_update", StateFilter(main_states.menu))
async def last_update_get(callback: CallbackQuery, state: FSMContext) -> None:
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		with open("./last_update_info.txt", "r") as update_info_file:
			last_update_data = update_info_file.read()

		await user_notification(chat_id=callback.from_user.id, text = last_update_data, auto_clean=False, parse=None)

	else:
		await end_session_notify(callback, state)

async def main() -> None:
	config = bot_config_read()["logs"]

	logging.basicConfig(
		level = logging.getLevelName(config["level"].upper()),
		filename = config["file"],
		filemode = "a",
		format="%(asctime)s %(levelname)s %(module)s %(funcName)s %(message)s")

	if redis_connect() != True:
		print("Error redis connect")
		logging.critical("Error redis connect")
	else:
		print("Redis PONG")
		logging.debug("Redis PONG")

	if psql_connect():
		print(psql_connect())
	else:
		print("PSQL connect error")
		logging.critical("PSQL connect error")

	print("Started")
	logging.info("Started")
	await dp.start_polling(bot)
	psql_cursor.close()
	psql_conn.close()
	print("Соединение с PSQL закрыто")

if __name__ == "__main__":
	asyncio.run(main())