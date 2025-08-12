import os
import asyncio
import logging
import json
import sys
import datetime

from hawk_python_sdk import Hawk

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, CallbackQuery, WebAppInfo, ContentType
from aiogram.utils.media_group import MediaGroupBuilder

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


bot = Bot(token=os.getenv("telegram_api_key"))
storage = RedisStorage.from_url(db_redis + os.getenv("redis_FSM_db"))
dp = Dispatcher(storage = storage)
webapp = WebAppInfo(url=os.getenv("webapp_url"))


class admin_plane(StatesGroup):
	menu = State()
	view_all_tickets = State()

class main_states(StatesGroup):
	menu = State()

class send_report_states(StatesGroup):
	print_text_report = State()
	media_verify = State()
	media_add = State()
	media_del = State()
	verify_report = State()

def menu_buttons_build(access_level: str, path: str):
	back_button = InlineKeyboardButton(text = "Назад (НЕ РЕАЛИЗОВАНО)⚠️", callback_data = "back")
	match path:
		case "back_only":
			main_buttons_finish_list = [[back_button]]

		case "main_menu":
			admin_plane_button = InlineKeyboardButton(text = "Панель администратора (НЕ РЕАЛИЗОВАНО)⚠️", callback_data = "admin_plane_menu")

			report_button = InlineKeyboardButton(text = "Сообщить о проблеме 📢 (НЕ РЕАЛИЗОВАНО)", callback_data = "report_menu")
			# notifications_center_button = InlineKeyboardButton(text = "Центр уведомлений (НЕ РЕАЛИЗОВАНО)⚠️", callback_data = "notifications_center_menu")
			end_session_button = InlineKeyboardButton(text = "Завершить сессию🚪", callback_data = "session_end")

			main_buttons = [[report_button], [end_session_button]]
			if access_level == "Admin":
				main_buttons_finish_list = [[admin_plane_button]] + main_buttons
			else:
				main_buttons_finish_list = main_buttons
		
		case "report_preview":
			change_text_button = InlineKeyboardButton(text = "Правка текста", callback_data = "report_menu")
			change_picture_button = InlineKeyboardButton(text = "Изменить вложения", callback_data = "change_picture")
			send_report_button = InlineKeyboardButton(text = "Отправить сообщение", callback_data = "send_report")

			main_buttons_finish_list = [[change_text_button], [change_picture_button], [send_report_button]]

		case "admin_plane":
			all_tickets_button = InlineKeyboardButton(text = "Все заявки", callback_data = "all_tickets_0")
			main_buttons_finish_list = [[all_tickets_button], [back_button]]

		case "all_tickets":
			main_buttons_finish_list = [
				InlineKeyboardButton(text = "<<", callback_data = "all_tickets_slide-left"),
				InlineKeyboardButton(text = ">>", callback_data = "all_tickets_slide-right")
			], [
				InlineKeyboardButton(text = "Поиск по номеру тикета", callback_data = "all_ticket-search")
			], [
				back_button
			]


	
	# if path == "main_menu":
	# 	admin_plane_button = InlineKeyboardButton(text = "Панель администратора (НЕ РЕАЛИЗОВАНО)⚠️", callback_data = "admin_plane_menu")

	# 	report_button = InlineKeyboardButton(text = "Сообщить о проблеме 📢", callback_data = "report_menu")
	# 	notifications_center_button = InlineKeyboardButton(text = "Центр уведомлений (НЕ РЕАЛИЗОВАНО)⚠️", callback_data = "notifications_center_menu")
	# 	end_session_button = InlineKeyboardButton(text = "Завершить сессию🚪", callback_data = "session_end")

	# 	main_buttons = [[report_button], [notifications_center_button], [end_session_button]]
	# 	if access_level == "Admin":
	# 		main_buttons_finish_list = [[admin_plane_button]] + main_buttons
	# 	else:
	# 		main_buttons_finish_list = main_buttons
	# elif path == "report_preview":
	# 	change_text_button = InlineKeyboardButton(text = "Правка текста", callback_data = "report_menu")
	# 	change_picture_button = InlineKeyboardButton(text = "Изменить вложения", callback_data = "change_picture")
	# 	send_report_button = InlineKeyboardButton(text = "Отправить сообщение", callback_data = "send_report")

	# 	main_buttons_finish_list = [[change_text_button], [change_picture_button], [send_report_button]]
	
	return InlineKeyboardMarkup(inline_keyboard = main_buttons_finish_list)

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
			update_admins_table(access_level, tg_username, chat_id)
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
	
	await clean_message(message.chat.id, message.message_id, 3)


# Temp command for state check
@dp.message(Command(commands=["state"]))
async def state_check(message: Message, state: FSMContext):
	current_state = await state.get_state()
	await message.reply(text=f"STATE: {current_state}")

@dp.message(Command(commands=["clear_state"]))
async def state_clear(message: Message, state: FSMContext):
	await state.clear()
	current_state = await state.get_state()
	await message.reply(text=f"STATE cleared: {current_state}")


@dp.callback_query(F.data == "admin_plane_menu")
async def admin_plane_menu(callback: CallbackQuery, state: FSMContext) -> None:
	current_state = await state.get_state()
	
	if check_session(session_db_redis, callback.from_user.username):
		update_session(session_db_redis, callback.from_user.username)

		await state.set_state(admin_plane.menu)

		keyboard = menu_buttons_build("Admin", "admin_plane")

		await bot.send_message(chat_id = callback.from_user.id, text = "Панель Администратора👑", reply_markup = keyboard)
		await clean_message(callback.from_user.id, callback.message.message_id, 1)


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

			await bot.send_message(chat_id = callback.from_user.id,
					text = f"Тикет: {ticket_number}\nСостояние: *{ticket_state}*\nОтправитель: @{ticket_owner_username}\n\n_{ticket_text}_",
					parse_mode = "Markdown", reply_markup = keyboard)
			await clean_message(callback.from_user.id, callback.message.message_id, 12)
		
		else:
			keyboard = menu_buttons_build(None, "back_only")
			await bot.send_message(chat_id = callback.from_user.id, text = f"Тикеты не обнаружены", reply_markup = keyboard)
	
	elif state_ticket_action == "slide-left":
		print("decr")
	
	elif state_ticket_action == "slide-right":
		state_ticket_number = await state.get_data()
		print(state_ticket_number["ticket_number"])


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


async def admin_notification(type_message: str, work_id: int) -> None:
	psql_cursor.execute(f"""SELECT chat_id FROM "Admins table";""")
	admin_raw_list = psql_cursor.fetchall()
	admin_list = [item[0] for item in admin_raw_list]
	if type_message == "ticket":

		delete_notification_button = [[InlineKeyboardButton(text = "Удалить уведомление", callback_data = "delete_notification")]]
		delete_keyboard = InlineKeyboardMarkup(inline_keyboard = delete_notification_button)

		for admin_chat_id in admin_list:
			msg = await bot.send_message(chat_id = admin_chat_id, text = f"Создано новое обращение по пробеме: {work_id}", reply_markup = delete_keyboard)
			tmp_db_redis.lpush("notifications", f"[{msg.chat.id}, {msg.message_id}, {str(datetime.datetime.now())}]")
		

@dp.callback_query(F.data == "delete_notification")
async def delete_notification(callback: CallbackQuery) -> None:
	await clean_message(callback.from_user.id, callback.message.message_id, 1)


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
		logging.debug(f"Ошибка при отправке запроса SQL")
	
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
		logging.debug(f"Ошибка {rowcount} при отправке запроса SQL")	
	return 0


async def main_menu_cal(callback: CallbackQuery, state: FSMContext) -> None:	
	update_session(session_db_redis, callback.from_user.username)

	await state.clear()
	await state.set_state(main_states.menu)
	
	user_data = load_user_data(session_db_redis, callback.from_user.username, ["ldap_fullname", "access_level"])
	await bot.send_message(chat_id = callback.from_user.id, text = f"Добро пожаловать *{user_data["ldap_fullname"]}*!\nУровень доступа: _{user_data["access_level"]}_", parse_mode = 'Markdown', reply_markup = menu_buttons_build(user_data["access_level"], "main_menu"))
	
	await clean_message(callback.from_user.id, callback.message.message_id, 12)


@dp.callback_query(F.data == 'send_report', StateFilter(send_report_states.verify_report))
async def send_report_notify(callback: CallbackQuery, state: FSMContext) -> None:
	update_session(session_db_redis, callback.from_user.username)

	state_data = await state.get_data()
	await state.clear()
	await state.set_state(main_states.menu)

	user_data = load_user_data(session_db_redis, callback.from_user.username, ["chat_id", "tg_username", "ldap_fullname", "access_level"])
	report_num = await send_report(state_data, user_data)

	delete_notification_button = [[InlineKeyboardButton(text = "Удалить уведомление", callback_data = "delete_notification")]]
	delete_keyboard = InlineKeyboardMarkup(inline_keyboard = delete_notification_button)

	logging.debug(f"Пользователь {callback.from_user.username} отправил репорт. State={await state.get_state()}. State_data={state_data}")
	await bot.send_message(chat_id = callback.from_user.id, text = f"Ваш запрос успешно отправлен!\nНомер запроса: *{report_num}*", parse_mode = 'Markdown', reply_markup = delete_keyboard)
	tmp_db_redis.lpush("notifications", f"[{callback.from_user.id}, {callback.message.message_id}, {str(datetime.datetime.now())}]")

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

		await bot.send_message(chat_id = callback.from_user.id, text = (f"Пожалуйста опишите свою проблему\nВаше предыдущее сообщение:\n_{state_data["text"]}_" if state_data_text else "Пожалуйста опишите свою проблему"), parse_mode = 'Markdown', reply_markup = ReplyKeyboardRemove())
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