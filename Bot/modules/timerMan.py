import asyncio
import json
import redis
import logging
import os
import datetime

from dotenv import load_dotenv
from aiogram import Bot
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

load_dotenv()

bot = Bot(token=os.getenv("telegram_api_key"))


def bot_config_read() -> dict:
	with open("./config.json") as config_file:
		return json.load(config_file)

def redis_connect(session_db_redis) -> bool:
	return session_db_redis.ping()

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


async def main() -> None:
	print("TimerMan started")
	config = bot_config_read()["timerman"]["logs"]
	logging.basicConfig(
		level = logging.getLevelName(config["level"].upper()),
		filename = config["file"],
		filemode = "a",
		format="%(asctime)s %(levelname)s %(module)s %(message)s")
	await asyncio.gather(session_killer(), clean_notification())

if __name__ == "__main__":
	asyncio.run(main())