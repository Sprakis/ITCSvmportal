import json
from ldap3 import Server, Connection
import logging
import os

def bot_config_read() -> dict:
	with open("./config.json") as config_file:
		return json.load(config_file)

def ldap_logon(credentionals: dict[str]) -> dict:
	# Получение учетных данных пользователя
	user_username = credentionals["login"]
	user_password = credentionals["pass"]

	#Проверка на пустое значение логина или пароля
	if not len(user_username) or not len(user_password):
		return 0, None, user_username, None
	
	# Чтение конфига и данных домена
	config = bot_config_read()["ldap"]
	dc = list(map(str, os.getenv("ldap_dc").split('.')))
	domain = os.getenv("ldap_domain")
	user_group = config["user_group"]
	admin_group = config["admin_group"]

	# Парсинг домена в формат DN атрибутов
	sep = ',DC='
	dc_str = sep.join(dc)
	dc_str = sep[1:] + dc_str

	# Последовательная проверка авторизации на контроллерах домена
	for ldap_ip in config["ip"]:
		ldap_server = Server(ldap_ip)
		logging.debug(f"Новое LDAP соединение: LDAP://{ldap_ip}@{domain}\\{user_username}")
		ldap_conn = Connection(ldap_server, user= f"{domain}\\{user_username}", password = user_password)
		# Проверка логина
		if ldap_conn.bind():
			logging.debug(f"LDAP://{ldap_ip}@{domain}\\{user_username} авторизация успешна")
			# Выгрузка атрибутов с ldap сервера
			ldap_conn.search(search_base=f'{dc_str}', search_filter=f"(sAMAccountName={user_username})", attributes = ["memberOf", "cn"])
			dn_user = ldap_conn.response[0]['dn']
			user_member_groups = ldap_conn.response[0]['attributes']['memberOf']
			fullname = ldap_conn.response[0]['attributes']['cn']
			logging.debug(f"LDAP://{ldap_ip}@{domain}\\{user_username}:\nDN={dn_user}\nUser groups={user_member_groups}\nFullname={fullname}")

			for member_group in user_member_groups:
				if user_group in member_group:
					group = "User"
					break
				elif admin_group in member_group:
					group = "Admin"
					break
				else:
					group = None
			logging.debug(f"LDAP://{ldap_ip}@{domain}\\{user_username}:\nUser Priv={group}")
			return 1, group, user_username, fullname
		else:
			logging.debug(f"Неверные данные для LDAP://{ldap_ip}@{domain}\\{user_username}")
	return 0, None, user_username, None