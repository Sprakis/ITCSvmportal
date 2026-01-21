import asyncio
import json
import redis
import logging
import os
import datetime

from dotenv import load_dotenv
from aiogram import Bot
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

from paloalto_con import change_internet_on_ip

load_dotenv()

bot = Bot(token=os.getenv("telegram_api_key"))


def bot_config_read() -> dict:
	with open("./config.json") as config_file:
		return json.load(config_file)

def redis_connect(session_db_redis) -> bool:
	return session_db_redis.ping()

async def user_notification(chat_id: int, text: str, parse = 'Markdown') -> None:
	delete_notification_button = [[InlineKeyboardButton(text = "Удалить уведомление", callback_data = "delete_notification")]]
	delete_keyboard = InlineKeyboardMarkup(inline_keyboard = delete_notification_button)

	await bot.send_message(chat_id=chat_id, text = text, parse_mode = parse, reply_markup=delete_keyboard)

async def session_killer() -> None:
	while True:
		logging.debug(f"Start Session Killer")
		config = bot_config_read()["databases"]["redis"]
		session_db_redis = redis.StrictRedis(
			host=config["url"],
			port=config["port"],
			password = os.getenv("redis_password"),
			db = os.getenv("redis_session_db"),
			decode_responses=True
		)

		logging.debug(f"Check Redis")
		if redis_connect(session_db_redis) != True:
			print("Error redis connect")
			logging.critical("Error redis connect")

		time_out = bot_config_read()["timerman"]["session_seconds_timeout"]

		logging.debug(f"Start read DB")
		logging.debug(f"DB len is {session_db_redis.llen("active_sessions")}")
		for session_hash in session_db_redis.lrange("active_sessions", 0, -1):
			logging.debug(f"Check {session_hash}")
			time_calc = datetime.datetime.strptime(session_db_redis.hget(session_hash, "session_update_time"), '%Y-%m-%d %H:%M:%S.%f') + datetime.timedelta(seconds = time_out)
			if time_calc <= datetime.datetime.now():
				try:
					session_db_redis.lrem("active_sessions", 0, session_hash)
					logging.info(f"Сессия {session_hash} удалена из активных")
					chat_id = session_db_redis.hget(session_hash, "chat_id")
					username = session_db_redis.hget(session_hash, "tg_username")
					session_db_redis.hdel(session_hash, 'tg_username', 'chat_id', 'ldap_username', 'ldap_fullname', 'access_level', 'session_update_time')
					logging.debug(f"Данные сессии {session_hash} удалены")
				except:
					logging.error(f"Ошибка при авточистке сессии {session_hash}")
					pass
				if chat_id:
					webapp = WebAppInfo(url=os.getenv("webapp_url"))

					login_button = [KeyboardButton(text = f"Авторизироваться как {username}", web_app = webapp)]
					login_keyboard = ReplyKeyboardMarkup(keyboard = [login_button], resize_keyboard=True)
					
					await bot.send_message(chat_id = chat_id, text = "Ваша сессия устарела⌛\nПожалуйста пройдите авторизацию", reply_markup = login_keyboard)
					logging.debug(f"Сообщение направлено пользователю {username}")
		await asyncio.sleep(bot_config_read()["timerman"]["check_session_pause"])
			

async def clean_notification() -> None:
	while True:
		logging.debug(f"Start clean_notification")
		config = bot_config_read()["databases"]["redis"]
		tmp_db_redis = redis.StrictRedis(
			host=config["url"],
			port=config["port"],
			password = os.getenv("redis_password"),
			db = os.getenv("redis_tmp_db"),
			decode_responses=True
		)
		logging.debug(f"Check Redis")
		if redis_connect(tmp_db_redis) != True:
			print("Error redis connect")
			logging.critical("Error redis connect")

		time_out = bot_config_read()["timerman"]["notification_delete_timer_sec"]

		logging.debug(f"Start read notification DB")
		logging.debug(f"Notification DB len is {tmp_db_redis.llen("notifications")}")
		for notification_raw in tmp_db_redis.lrange("notifications", 0, -1):
			notification = [item.strip().strip("'") for item in notification_raw[1:-1].split(',')]
			
			logging.debug(f"Check {notification}")
			time_calc = datetime.datetime.strptime(list(notification)[2], '%Y-%m-%d %H:%M:%S.%f') + datetime.timedelta(seconds = time_out)
			if time_calc <= datetime.datetime.now():
				try:
					tmp_db_redis.lrem("notifications", 0, notification_raw)
					await bot.delete_message(chat_id = notification[0], message_id = notification[1])
					logging.debug(f"Notification {notification} очищено")
				except:
					logging.error(f"Ошибка при авточистке notification {notification}")
					pass
		await asyncio.sleep(bot_config_read()["timerman"]["notification_delete_timer_sec"])


async def tasks_reader() -> None:
	while True:
		logging.debug(f"Start tasks_reader")
		psql_cursor.execute(f"""SELECT id, owner_id, data FROM "Tasks table" WHERE type = 'internet_access' and status = 'Waiting'""")
		tasks_list =  psql_cursor.fetchall()
		logging.debug(f"Список доступных задач: {tasks_list}")

		

		if len(tasks_list):
			work_data = []
			for task in tasks_list:
				logging.debug(f"Задача {task[0]} помечена как Running")
				psql_cursor.execute(f"""UPDATE "Tasks table" SET status = 'Running' WHERE id = '{task[0]}'""")
				psql_cursor.execute(f"""UPDATE "Tasks table" SET last_change_date = '{datetime.datetime.now()}' WHERE id = '{task[0]}'""")
				work_data.append({"id": task[0],
					  "owner_id": task[1],
					  "data": task[2]})
				
			work_result, work_result_data = change_internet_on_ip(work_data)
			if work_result:
				logging.debug(f"Пул задач выполнен. Результат = {work_result_data}")
				for task_result in work_result_data:
					if task_result["status"] == "F":
						logging.debug(f"Задача {task_result["id"]} - успешно выполнена. Задача помечена как Complete")
						psql_cursor.execute(f"""UPDATE "Tasks table" SET status = 'Complete' WHERE id = '{task_result["id"]}'""")
						logging.debug(f"Создатель задачи {task_result["id"]} уведомлен о завершении")
						await user_notification(chat_id=task_result["owner_id"], text=f"Задача с номером {task_result["id"]} - Выдача доступа в интернет\n*Выполнена*")
					else:
						logging.debug(f"Задача {task_result["id"]} - выполнена с ошибками. Задача помечена как Waiting")
						psql_cursor.execute(f"""UPDATE "Tasks table" SET status = 'Waiting', comment = 'Finish with Errors' WHERE id = '{task_result["id"]}'""")
			else:
				logging.debug(f"Пул задач выполнен. Результат = {work_result_data}. Задачи помечены как Waiting")
				for task in tasks_list:
					psql_cursor.execute(f"""UPDATE "Tasks table" SET status = 'Waiting', comment = 'Finish with Errors' WHERE id = '{task[0]}'""")
		else:
			pass

		await asyncio.sleep(bot_config_read()["timerman"]["check_new_tasks"])


import psycopg2
psql_config = bot_config_read()["databases"]["psql"]
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

async def main() -> None:
	print("TimerMan started")
	config = bot_config_read()["timerman"]["logs"]
	logging.basicConfig(
		level = logging.getLevelName(config["level"].upper()),
		filename = config["file"],
		filemode = "a",
		format="%(asctime)s %(levelname)s %(module)s %(funcName)s %(message)s")
	
	if psql_connect():
		print(psql_connect())
	else:
		print("PSQL connect error")
		logging.critical("PSQL connect error")

	await asyncio.gather(session_killer(), clean_notification(), tasks_reader())

if __name__ == "__main__":
	asyncio.run(main())