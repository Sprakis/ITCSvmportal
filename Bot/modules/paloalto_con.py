import json
import os
import requests
import urllib3
urllib3.disable_warnings()
import asyncio

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
	raw_response = requests.post(url = f"https://{config["ip"]}/api", headers = headers, data = body, verify=False)
	response = raw_response.text.split("<key>")[1].split("</key>")
	return response[0]

async def ip_deep_search(members: list, answer: list, api_key, config) -> list:
	headers = {
		"X-PAN-KEY": api_key
	}
	params_deep = {
			"name": config["internet_group"],
			"location": config["location_type"],
			"vsys": config["location_name"]
	}
	raw_response = requests.get(url = f"https://{config["ip"]}/restapi/{config["api_version"]}/Objects/AddressGroups", headers=headers, params = params_deep, verify=False)
	response = raw_response.json()["result"]["entry"][0]["static"]["member"]
	for i in range(len(answer)):
		if members[i]:
			if members[i] not in response:
				answer[i] = False
	
	return answer


async def get_ip_net_info(ip_list: list) -> list:
	config = bot_config_read()["paloalto"]
	api_key = get_api_key()
	headers = {
		"X-PAN-KEY": api_key
	}
	params = {
		"location": config["location_type"],
		"vsys": config["location_name"]
	}
	raw_response = requests.get(url = f"https://{config["ip"]}/restapi/{config["api_version"]}/Objects/Addresses", headers=headers, params = params, verify=False)
	data = raw_response.json()["result"]["entry"]
	deep_search_ip = []
	flag_matrix = []
	search_flag = False
	for ip in ip_list:
		for ip_object in data:
			if ip == ip_object["ip-netmask"]:
				search_flag = True
				obj_name = ip_object["@name"]
		if search_flag:
			deep_search_ip.append(obj_name)
			flag_matrix.append(True)
		else:
			deep_search_ip.append(None)
			flag_matrix.append(False)
		search_flag = False
	answer = await ip_deep_search(deep_search_ip, flag_matrix, api_key, config)
	return answer