import hashlib
import datetime
import logging

def new_session(session_db_redis, tg_username: str, chat_id: int, ldap_username: str, ldap_fullname: str, access_level: str) -> bool:
	h_user = hashlib.sha256(bytes(f'{tg_username}', 'UTF-8')).hexdigest()
	logging.debug(f"User: {tg_username}, session: {h_user}")
	
	session_keys = {
		'tg_username': tg_username,
		'chat_id': chat_id,
		'ldap_username': ldap_username,
		'ldap_fullname': ldap_fullname,
		'access_level': access_level,
		'session_update_time': str(datetime.datetime.now())
	}

	try:
		logging.debug(session_db_redis.lrange("active_sessions", 0, session_db_redis.llen("active_sessions")))
		if h_user not in session_db_redis.lrange("active_sessions", 0, session_db_redis.llen("active_sessions")):
			session_db_redis.lpush("active_sessions", h_user)
			session_db_redis.hset(h_user, mapping = session_keys)
			logging.debug(f"Сессия {h_user} добавлена в активные")
			logging.debug(f"Сессия {h_user} зарегистрирована с параметрами:\n{session_keys}")
		else:
			logging.debug(f"Сессия {h_user} уже зарегистрирована. Игнорирование")
			session_db_redis.hset(h_user, mapping = session_keys)
			logging.debug(f"Сессия {h_user} обновлена с параметрами:\n{session_keys}")
		return 1
	except:
		logging.critical(f"Ошибка при создании новой сессии {h_user}")
		return 0

def update_session(session_db_redis, tg_username: str) -> None:
	h_user = hashlib.sha256(bytes(f'{tg_username}', 'UTF-8')).hexdigest()
	try:
		session_db_redis.hset(h_user, key = "session_update_time", value = str(datetime.datetime.now()))
		logging.debug(f"Сессия {h_user} обновлена. Новый срок: {str(datetime.datetime.now())}")
	except:
		logging.critical(f"Ошибка при обновлении сессии {h_user}")
	return 0

def load_user_data(session_db_redis, tg_username: str, keys: list) -> dict:
	h_user = hashlib.sha256(bytes(f'{tg_username}', 'UTF-8')).hexdigest()
	answer = {}
	logging.debug(f"load_user_data for {h_user}\nKeys: {keys}")
	for key in keys:
		answer.update({f"{key}": session_db_redis.hget(h_user, key).decode('utf-8')})
	logging.debug(f"load_user_data for {h_user}\nAnswer: {answer}")
	return answer

def check_session(session_db_redis, tg_username: str) -> bool:
	h_user = hashlib.sha256(bytes(f'{tg_username}', 'UTF-8')).hexdigest()

	try:
		logging.debug(f"Проверка существования сессии {h_user}")
		return session_db_redis.hexists(h_user, "tg_username")
	except:
		logging.debug(f"Ошибка при проверке существования сессии {h_user}")
	return 0

def exit_session(session_db_redis, tg_username: str) -> bool:
	h_user = hashlib.sha256(bytes(f'{tg_username}', 'UTF-8')).hexdigest()
	try:
		session_db_redis.lrem("active_sessions", 0, h_user)
		logging.debug(f"Сессия {h_user} удалена из активных")
		session_db_redis.hdel(h_user, 'tg_username', 'chat_id', 'ldap_username', 'ldap_fullname', 'access_level', 'session_update_time')
		logging.debug(f"Данные сессии {h_user} удалены")
		return 1
	except:
		return 0