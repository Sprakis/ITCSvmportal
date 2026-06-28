import json
import requests
import os
import urllib3
urllib3.disable_warnings()
import logging

def bot_config_read() -> dict:
	with open("config.json") as config_file:
		return json.load(config_file)

def login() -> tuple:
	config = bot_config_read()["check_point"]
	body = {
		"api-key": os.getenv("check_point_api_key"),
	}
	logging.debug(f"POST Запрос в CheckPoint: https://{config["ip"]}/web_api/login\nPayload: {body}")
	try:
		response = requests.post(url=f"https://{config["ip"]}/web_api/login", json=body, verify=False)
	except Exception as e:
		logging.error(f"Ошибка запроса! {e}")
		return "Error", None
	logging.debug(f"Успешный запрос! Код: {response.status_code} | Ответ: {response.text}")
	sid = response.json()["sid"]
	s_uid = response.json()["uid"]
	return sid, s_uid

def logout(sid) -> None:
	config = bot_config_read()["check_point"]
	headers = {
		"X-chkp-sid": sid
	}
	body = {}
	logging.debug(f"POST Запрос в CheckPoint: https://{config["ip"]}/web_api/logout\nHeaders: {headers}\nPayload: {body}")
	try:
		response = requests.post(url=f"https://{ip}/web_api/logout", headers=headers, json=body, verify=False)
	except Exception as e:
		logging.error(f"Ошибка запроса! {e}")
		return None
	logging.debug(f"Успешный запрос! Код: {response.status_code} | Ответ: {response.text}")

def get_ip_address_ranges(sid: str) -> list:
	config = bot_config_read()["check_point"]
	headers = {
		"X-chkp-sid": sid
	}
	body = {
		"name": config["internet_group"],
		"show-as-ranges": True
	}
	logging.debug(f"POST Запрос в CheckPoint: https://{config["ip"]}/web_api/show-group\nHeaders: {headers}\Payload: {body}")
	response = requests.post(url=f"https://{config["ip"]}/web_api/show-group", headers=headers, json=body, verify=False)
	logging.debug(f"Успешный запрос! Код: {response.status_code} | Ответ: {response.text}")
	return response.json()["ranges"]["ipv4"]


def convert_ipv4(ip) -> tuple:
	return tuple(int(n) for n in ip.split("."))

def check_ipv4_range(ip_start, ip_end, ip) -> bool:
	return convert_ipv4(ip_start) < convert_ipv4(ip) <= convert_ipv4(ip_end)

async def get_ip_net_info_cp(ip_list: list) -> list:
	sid, s_uid = login()
	if sid == "Error":
		return "Error"
	data = get_ip_address_ranges(sid)
	logging.debug(f"Полный лист {ip_list}")
	flag_matrix = []
	search_flag = False
	for ip in ip_list:
		logging.debug(f"Обработка {ip}")
		for range_object in data:
			if check_ipv4_range(range_object["start"], range_object["end"], ip):
				search_flag = True
				logging.debug(f"Совпадение найдено!\n{range_object}")
		if search_flag:
			flag_matrix.append(True)
		else:
			flag_matrix.append(False)
		search_flag = False
	logging.debug(f"Конечная матрица: {flag_matrix}")
	logout(sid)
	return flag_matrix