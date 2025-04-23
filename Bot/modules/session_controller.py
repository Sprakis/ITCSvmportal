import hashlib
import datetime
import logging

def new_session(session_db_redis, tg_username: str, chat_id: int, ldap_username: str, access_level: str) -> bool:
	h_user = hashlib.sha256(bytes(f'{tg_username}', 'UTF-8')).hexdigest()
	logging.debug(f"User: {tg_username}, session: {h_user}")
	
	session_keys = {
		'tg_username': tg_username,
		'chat_id': chat_id,
		'ldap_username': ldap_username,
		'access_level': access_level,
		'session_update_time': str(datetime.datetime.now())
	}

	try:
		session_db_redis.lpush("active_sessions", h_user)
		logging.debug(f"Сессия {h_user} добавлена в активные")
		session_db_redis.hset(h_user, mapping = session_keys)
		logging.debug(f"Сессия {h_user} зарегистрирована с параметрами:\n{session_keys}")
		return 1
	except:
		logging.critical(f"Ошибка при создании новой сессии {h_user}")
		return 0

def update_session():
	return 1

def exit_session(session_db_redis, tg_username: str) -> bool:
	h_user = hashlib.sha256(bytes(f'{tg_username}', 'UTF-8')).hexdigest()
	try:
		session_db_redis.lrem("active_sessions", 0, h_user)
		logging.debug(f"Сессия {h_user} удалена из активных")
		session_db_redis.hdel(h_user, 'tg_username', 'chat_id', 'ldap_username', 'access_level', 'session_update_time')
		logging.debug(f"Данные сессии {h_user} удалены")
		return 1
	except:
		return 0