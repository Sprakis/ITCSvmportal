import requests
import urllib3
urllib3.disable_warnings()
import os
import json


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
		ip_address_list(address: "{ip}") {{
		  address, role, status, custom_fields, tenant {{
		  name
		  }}
		}}
}}
"""
	}
	config = bot_config_read()["netbox"]
	response = requests.get(url = f"https://{config["address"]}/graphql/", headers=headers, json = body, verify=False)
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
		"query": f"""
query{{
		ip_address_list(address: "{ip}") {{
		  address, role, status, custom_fields, tenant {{
		  name
		  }}
		}}
}}
"""
	}