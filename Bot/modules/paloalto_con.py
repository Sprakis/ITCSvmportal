import json
import os
import requests
import urllib3
urllib3.disable_warnings()
import asyncio
import logging

def bot_config_read() -> dict:
	with open("./config.json") as config_file:
		return json.load(config_file)

def get_api_key() -> str:
	config = bot_config_read()["paloalto"]
	
	headers = {
		"Content-Type": "application/x-www-form-urlencoded"
	}
	body = {
		"type": "keygen",
		"user": os.getenv("paloalto_login"),
		"password": os.getenv("paloalto_password")
	}
	logging.debug(f"POST Запрос в PaloAlto: https://{config["ip"]}/api\nHeaders: {headers}\nPayload: {body}")
	try:
		raw_response = requests.post(url = f"https://{config["ip"]}/api", headers = headers, data = body, verify=False)
	except:
		return "Error"
	logging.debug(f"Успешный запрос! Код: {raw_response.status_code} | Ответ: {raw_response.text}")
	response = raw_response.text.split("<key>")[1].split("</key>")
	return response[0]

def commit(api_key: str) -> bool:
	logging.debug(f"Запрос на Commit")
	config = bot_config_read()["paloalto"]
	headers = {
		"X-PAN-KEY": api_key
	}
	body = {
		"type": "commit"
	}
	params = {
		"cmd": f"<commit><partial><admin><member>{os.getenv("paloalto_login")}</member></admin></partial></commit>"
	}
	raw_response = requests.post(url = f"https://{config["ip"]}/api", headers = headers, params= params, data = body, verify=False)
	logging.debug(f"Успешный запрос! Код: {raw_response.status_code} | Ответ: {raw_response.text}")
	if raw_response.status_code == 200:
		return True
	else:
		return False

async def ip_deep_search(members: list, answer: list, api_key, config) -> list:
	headers = {
		"X-PAN-KEY": api_key
	}
	params_deep = {
			"name": config["internet_group"],
			"location": config["location_type"],
			"vsys": config["location_name"]
	}
	logging.debug(f"GET Запрос в PaloAlto: https://{config["ip"]}/restapi/{config["api_version"]}/Objects/AddressGroups\nHeaders: {headers}\nParams: {params_deep}")
	raw_response = requests.get(url = f"https://{config["ip"]}/restapi/{config["api_version"]}/Objects/AddressGroups", headers=headers, params = params_deep, verify=False)
	logging.debug(f"Успешный запрос! Код: {raw_response.status_code} | Ответ: {raw_response.text}")
	response = raw_response.json()["result"]["entry"][0]["static"]["member"]
	for i in range(len(answer)):
		if members[i]:
			if members[i] not in response:
				answer[i] = False
	logging.debug(f"Результат глубокого поиска {answer}")
	return answer


def get_ip_address_list(api_key: str) -> list:
	config = bot_config_read()["paloalto"]
	headers = {
		"X-PAN-KEY": api_key
	}
	params = {
		"location": config["location_type"],
		"vsys": config["location_name"]
	}
	logging.debug(f"GET Запрос в PaloAlto: https://{config["ip"]}/restapi/{config["api_version"]}/Objects/Addresses\nHeaders: {headers}\nParams: {params}")
	response = requests.get(url = f"https://{config["ip"]}/restapi/{config["api_version"]}/Objects/Addresses", headers=headers, params = params, verify=False)
	logging.debug(f"Успешный запрос! Код: {response.status_code} | Ответ: {response.text}")
	return response.json()["result"]["entry"]

async def get_ip_net_info(ip_list: list) -> list:
	config = bot_config_read()["paloalto"]
	api_key = get_api_key()
	if api_key == "Error":
		return "Error"
	data = get_ip_address_list(api_key)
	deep_search_ip = []
	flag_matrix = []
	search_flag = False
	logging.debug(f"Полный лист {ip_list}")
	for ip in ip_list:
		logging.debug(f"Обработка {ip}")
		for ip_object in data:
			if ip == ip_object["ip-netmask"]:
				search_flag = True
				obj_name = ip_object["@name"]
				logging.debug(f"Совпадение найдено!\n{obj_name}")
		if search_flag:
			logging.debug(f"Добавление {obj_name} в список глубокого поиска")
			deep_search_ip.append(obj_name)
			flag_matrix.append(True)
		else:
			deep_search_ip.append(None)
			flag_matrix.append(False)
		search_flag = False
	logging.debug(f"Список глубокого поиска: {deep_search_ip}\nНачальная матрица глубокого поиска: {flag_matrix}")
	answer = await ip_deep_search(deep_search_ip, flag_matrix, api_key, config)
	return answer


def get_group_members(api_key: str, group: str) -> dict:
	config = bot_config_read()["paloalto"]
	headers = {
		"X-PAN-KEY": api_key
	}
	params = {
		"name": group,
		"location": config["location_type"],
		"vsys": config["location_name"]
	}
	logging.debug(f"GET Запрос в PaloAlto: https://{config["ip"]}/restapi/{config["api_version"]}/Objects/Addresses\nHeaders: {headers}\nParams: {params}")
	response = requests.get(url=f"https://{config["ip"]}/restapi/{config["api_version"]}/Objects/AddressGroups", headers=headers, params = params, verify=False)
	logging.debug(f"Успешный запрос! Код: {response.status_code} | Ответ: {response.text}")
	if response.status_code == 200:
		return response.json()["result"]["entry"][0]["static"]["member"]
	else:
		return None

def create_address_object(api_key: str, address: str, object_name: str, exists_addresses: list) -> bool:
	logging.debug(f"Запрос на создание объекта - {object_name}")
	config = bot_config_read()["paloalto"]
	headers = {
		"X-PAN-KEY": api_key
	}
	for exist_address in exists_addresses:
		if exist_address["@name"] == object_name:
			logging.debug(f"Объект {object_name} уже существует")
			return True
		if exist_address["ip-netmask"] == address:
			logging.debug(f"Адресс {address} уже существует, имя объекта будет обновлено")
			params = {
				"name": exist_address["@name"],
				"location": config["location_type"],
				"vsys": config["location_name"]
			}
			payload = {
				"entry": {
					"@name": object_name,
					"tag": {
						"member": [config["internet_objects_tag"]]
					},
					"ip-netmask": address
				}
			}
			logging.debug(f"Запрос на обновление объекта - {exist_address["@name"]}. Новое название - {object_name}")
			raw_response = requests.put(url=f"https://{config["ip"]}/restapi/{config["api_version"]}/Objects/Addresses", headers=headers, params = params, json=payload, verify=False)
			logging.debug(f"Успешный запрос! Код: {raw_response.status_code} | Ответ: {raw_response.text}")
			if raw_response.status_code == 200:
				return True
			else:
				return False
	params = {
		"name": object_name,
		"location": config["location_type"],
		"vsys": config["location_name"]
	}
	payload = {
		"entry": {
			"@name": object_name,
			"tag": {
				"member": ["internet_for_datacenter_VM"]
			},
			"ip-netmask": address
		}
	}
	logging.debug(f"Запрос на создание объекта - {object_name}")
	raw_response = requests.post(url=f"https://{config["ip"]}/restapi/{config["api_version"]}/Objects/Addresses", headers=headers, params = params, json=payload, verify=False)
	logging.debug(f"Успешный запрос! Код: {raw_response.status_code} | Ответ: {raw_response.text}")
	if raw_response.status_code == 200:
		return True
	else:
		return False

def delete_address_object(api_key: str, address: str, object_name: str, exists_addresses: list) -> bool:
	logging.debug(f"Запрос на удаление объекта - {object_name}")
	config = bot_config_read()["paloalto"]
	headers = {
		"X-PAN-KEY": api_key
	}
	for exist_address in exists_addresses:
		params = {
				"name": exist_address["@name"],
				"location": config["location_type"],
				"vsys": config["location_name"]
		}
		if exist_address["@name"] == object_name:	
			logging.debug(f"Объект {object_name} существует. Объект будет удален")
			logging.debug(f"Запрос на удаление объекта - {exist_address["@name"]}")
			raw_response = requests.delete(url=f"https://{config["ip"]}/restapi/{config["api_version"]}/Objects/Addresses", headers=headers, params = params, verify=False)
			logging.debug(f"Успешный запрос! Код: {raw_response.status_code} | Ответ: {raw_response.text}")
			if raw_response.status_code == 200:
				return True
			else:
				return False
		if exist_address["ip-netmask"] == address:
			logging.debug(f"Адресс {address} существует. Объект будет удален")
			raw_response = requests.delete(url=f"https://{config["ip"]}/restapi/{config["api_version"]}/Objects/Addresses", headers=headers, params = params, verify=False)
			logging.debug(f"Успешный запрос! Код: {raw_response.status_code} | Ответ: {raw_response.text}")
			if raw_response.status_code == 200:
				return True
			else:
				return False
	return True

def change_internet_on_ip(work_data: dict) -> tuple:
	config = bot_config_read()["paloalto"]
	api_key = get_api_key()
	if api_key == "Error":
		return False, None
	internet_group_members = get_group_members(api_key, config["internet_group"])
	exists_addresses = get_ip_address_list(api_key)
	if internet_group_members:
		task_result = []
		for task in work_data:
			logging.debug(f"Обработка задачи: {task["id"]} - {task["data"]}")
			task_result.append({"id": task["id"], "owner_id": task["owner_id"], "status": "S"})
			addresses = json.loads(task["data"])
			for ip in addresses:
				object_name = f"host_{ip["address"].split("/")[0]}_{ip["machine_name"][0].split("[")[0].replace(" ", "", -1)}"
				logging.debug(f"Обработка адреса: {ip["address"]} - {object_name}")
				if ip["internet"]:
					logging.debug(f"Разрешение доступа для {ip["address"]}")
					if create_address_object(api_key, ip["address"].split("/")[0], object_name, exists_addresses):
						logging.debug(f"Объект {object_name} существует")
						if object_name not in internet_group_members:
							internet_group_members.append(object_name)
							logging.debug(f"Объект {object_name} добавлен в группу {config["internet_group"]}")
							if addresses.index(ip) == (len(addresses) - 1):
								logging.debug(f"Статус объекта {object_name} - F")
								task_result[work_data.index(task)].update({"status": "F"})
							else:
								logging.debug(f"Статус объекта {object_name} - R")
								task_result[work_data.index(task)].update({"status": "R"})
						else:
							if addresses.index(ip) == (len(addresses) - 1):
								logging.debug(f"Статус объекта {object_name} - F")
								task_result[work_data.index(task)].update({"status": "F"})
							else:
								logging.debug(f"Статус объекта {object_name} - R")
								task_result[work_data.index(task)].update({"status": "R"})
				else:
					if object_name in internet_group_members:
						internet_group_members.remove(object_name)
						logging.debug(f"Объект {object_name} удален из группы {config["internet_group"]}")
						if addresses.index(ip) == (len(addresses) - 1):
							logging.debug(f"Статус объекта {object_name} - F")
							task_result[work_data.index(task)].update({"status": "F"})
						else:
							logging.debug(f"Статус объекта {object_name} - R")
							task_result[work_data.index(task)].update({"status": "R"})
					
					# if delete_address_object(api_key, ip["address"].split("/")[0], object_name, exists_addresses):
					# 	logging.debug(f"Объект {object_name} отсутствует")
						# if addresses.index(ip) == (len(addresses) - 1):
						# 	logging.debug(f"Статус объекта {object_name} - F")
						# 	task_result[work_data.index(task)].update({"status": "F"})
						# else:
						# 	logging.debug(f"Статус объекта {object_name} - R")
						# 	task_result[work_data.index(task)].update({"status": "R"})
	else:
		return None
	global_error_flag = True
	logging.debug(f"Проверка выполнения задач")
	for complete_task in task_result:
		logging.debug(f"Проверка {complete_task}")
		if complete_task["status"] == "F" or complete_task["status"] == "R":
			logging.debug(f"Флаг сменен на False")
			global_error_flag = False

	if not global_error_flag:
		headers = {
			"X-PAN-KEY": api_key
		}
		params = {
			"name": config["internet_group"],
			"location": config["location_type"],
			"vsys": config["location_name"]
		}
		payload = {
			"entry": {
				"static": {
					"member": internet_group_members
				},
				"@name": config["internet_group"],
				"tag": {
					"member": [config["internet_group_tag"]]
				}
			}
		}
		logging.debug(f"Применение нового состава {config["internet_group"]}")
		response = requests.put(url=f"https://{config["ip"]}/restapi/{config["api_version"]}/Objects/AddressGroups", headers=headers, params = params, json=payload, verify=False)
		logging.debug(f"Успешный запрос! Код: {response.status_code} | Ответ: {response.text}")
		if response.status_code == 200:
			logging.debug(f"Запрос на Commit")
			return commit(api_key), task_result
	logging.debug(f"Ошибка обработки запросов")
	return False, task_result
		