import requests
import urllib3
urllib3.disable_warnings()
import os
import json
import logging


def bot_config_read() -> dict:
	with open("./config.json") as config_file:
		return json.load(config_file)



def get_ip_info(ip: str) -> dict:
	headers = {"Content-Type": "application/json",
			"Accept": "application/json",
			"Authorization": f"Token {os.getenv("netbox_api_key")}"}
	body = {
		"query": f"""
		query{{
			ip_address_list(filters: {{
				address: {{
					starts_with: "{ip}"
				}}
			}})
			{{
				address,
				role,
				status,
				custom_fields,
				tenant {{
					name
				}}
			}}
		}}"""
	}
	config = bot_config_read()["netbox"]
	logging.debug(f"Запрос в Netbox: https://{config["address"]}/graphql/\nHeaders: {headers}\nPayload: {body}")
	response = requests.post(url = f"https://{config["address"]}/graphql/", headers=headers, json = body, verify=False)
	logging.debug(f"Успешный запрос! Код: {response.status_code} | Ответ: {response.text}")
	try:
		return response.json()["data"]["ip_address_list"][0]
	except:
		return None
	
def get_vm_info(vm: str) -> dict:
	headers = {
		"Content-Type": "application/json",
		"Accept": "application/json",
		"Authorization": f"Token {os.getenv("netbox_api_key")}"
	}
	body = {
		"query": f""""""
	}
	config = bot_config_read()["netbox"]
	logging.debug(f"Запрос в Netbox: https://{config["address"]}/graphql/\nHeaders: {headers}\nPayload: {body}")
	response = requests.post(url = f"https://{config["address"]}/graphql/", headers=headers, json = body, verify=False)
	logging.debug(f"Успешный запрос! Код: {response.status_code} | Ответ: {response.text}")
	try:
		return response.json()["data"]["ip_address_list"]
	except:
		return None