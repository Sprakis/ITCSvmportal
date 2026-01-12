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
					i_starts_with: "{ip}/"
				}}
			}})
			{{
				address,
				role,
				status,
				custom_fields,
				tenant {{
					name
				}},
				description
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
		"query": f"""query {{
  ip_address_list(filters: {{
    custom_field_data:{{
      path: "Machine_Name",
      lookup: {{
        string_lookup: {{
          i_contains: "{vm}"
        }}
      }}
    }}
  }}
  ) {{
    address,
    custom_fields,
    role,
    status,
    tenant {{
      name
    }}
  }}
}}"""
	}
	config = bot_config_read()["netbox"]
	logging.debug(f"Запрос в Netbox: https://{config["address"]}/graphql/\nHeaders: {headers}\nPayload: {body}")
	raw_response = requests.post(url = f"https://{config["address"]}/graphql/", headers=headers, json = body, verify=False)
	logging.debug(f"Успешный запрос! Код: {raw_response.status_code} | Ответ: {raw_response.text}")
	try:
		response = []
		all_vm = []
		for obj in raw_response.json()["data"]["ip_address_list"]:
			vm_names = obj["custom_fields"]["Machine_Name"].split(" | ")
			if vm_names[0] in all_vm:
				response[all_vm.index(vm_names[0],0,len(all_vm))]["networks"].append({"Machine_Name": vm_names,
					"Implementation_type": obj["custom_fields"]["Implementation_type"],
					"address": obj["address"],
					"role": obj["role"],
					"status": obj["status"],
					"tenant": obj["tenant"]["name"]})
			else:
				vm_names = obj["custom_fields"]["Machine_Name"].split(" | ")
				all_vm.append(vm_names[0])
				response.append({"Machine_Name": vm_names[0],
						"networks": [{"Machine_Name": vm_names,
					"Implementation_type": obj["custom_fields"]["Implementation_type"],
					"address": obj["address"],
					"role": obj["role"],
					"status": obj["status"],
					"tenant": obj["tenant"]["name"]}]})
	
		return response
	except:
		return ""