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

async def ip_deep_search(member, api_key, config) -> bool:
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
	for host in response:
		if host == member:
			return True
	return False

async def get_ip_net_info(ip: str) -> bool:
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
	for ip_object in data:
		if ip_object["ip-netmask"] == ip:
			return await ip_deep_search(ip_object["@name"], api_key, config)

	return False