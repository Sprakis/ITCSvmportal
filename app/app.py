import uvicorn
import json
import logging
import os

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from dotenv import load_dotenv

from modules.ldap_auth import ldap_logon
from modules.netbox_con import get_ip_info, get_vm_info
from modules.paloalto_con import get_ip_net_info_pa
from modules.checkpoint_con import get_ip_net_info_cp

class ip_list_item(BaseModel):
	ip_list: list

class vm_name_item(BaseModel):
	vm_name: str

def config_read() -> dict:
	with open("./config.json", "r") as config_file:
		return json.load(config_file)

load_dotenv()
config_db = config_read()["databases"]
config_app = config_read()["app"]

app = FastAPI()

api_server_keys = []
tg_bot_api_key = os.getenv("tg_bot_api_key")
if tg_bot_api_key:
	api_server_keys.append(tg_bot_api_key)

api_key = APIKeyHeader(name="X-Key")

def read_key(key: str = Depends(api_key)):
	if key not in api_server_keys:
		raise HTTPException(status_code=401, detail="Invalid API Key")
	return key

import psycopg2

psql_config = config_db["psql"]

psql_conn = psycopg2.connect(user = os.getenv("postsql_username"),
							 password = os.getenv("postsql_password"),
							 host = psql_config["url"],
							 port = psql_config["port"],
							 dbname = os.getenv("postsql_database"))
psql_conn.set_session(autocommit=True)


def database_request(request: str, fetch_type: str = None, data: dict = None) -> list:
	with psql_conn.cursor() as psql_cursor:
		if type(data) == int:
			psql_cursor.execute(request, [data])
		else:
			psql_cursor.execute(request, data)
		match fetch_type:
			case "one":
				return psql_cursor.fetchone()
			case "all":
				return psql_cursor.fetchall()
			case "rowcount":
				return psql_cursor.rowcount
			case "statusmessage":
				return psql_cursor.statusmessage
			case _:
				pass

def psql_connect_check() -> str:
	return database_request(request="SELECT version();", fetch_type="one")

def database_init() -> None:
	# Amin table
	if bool(database_request(request="""select * from information_schema.tables where table_name='Admins table';""", fetch_type="rowcount")):
		print("Admins table - Exist")
	else:
		database_request(request="""CREATE TABLE public."Admins table" (
		username character varying(24) NOT NULL,
		chat_id bigint NOT NULL,
		department text
	);""")
		print("Admins table - Created")
	
	# Reports table
	if bool(database_request(request="""select * from information_schema.tables where table_name='Reports table';""", fetch_type="rowcount")):
		print("Reports table - Exist")
	else:
		database_request(request="""CREATE TABLE public."Reports table" (
		text character varying(4096) NOT NULL,
		status character varying(6) NOT NULL,
		attachments_hashs text,
		chat_id bigint NOT NULL,
		username character varying(24) NOT NULL,
		"ID_rep" bigint NOT NULL,
		PRIMARY KEY ("ID_rep")
	);""")
		database_request(request="""CREATE SEQUENCE public."Reports table_ID_rep_seq" CYCLE INCREMENT 1 START 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1;""")
		database_request(request="""ALTER SEQUENCE public."Reports table_ID_rep_seq" OWNED BY public."Reports table"."ID_rep";""")
		database_request(request="""ALTER TABLE IF EXISTS public."Reports table" ALTER COLUMN "ID_rep" SET DEFAULT nextval('"Reports table_ID_rep_seq"'::regclass);""")
		print("Reports table - Created")

	# Requests table
	if bool(database_request(request="""select * from information_schema.tables where table_name='Requests table';""", fetch_type="rowcount")):
		print("Requests table - Exist")
	else:
		database_request(request="""CREATE TABLE public."Requests table" (
		"ID" bigint NOT NULL,
		type character varying(6) NOT NULL,
		owner_ldap_fullname character varying(30),
		owner_chat_id integer NOT NULL,
		owner_username character varying(30) NOT NULL,
		PRIMARY KEY ("ID")
	);""")
		database_request(request="""CREATE SEQUENCE public."Requests table_ID_seq" CYCLE INCREMENT 1 START 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1;""")
		database_request(request="""ALTER SEQUENCE public."Requests table_ID_seq" OWNED BY public."Requests table"."ID";""")
		database_request(request="""ALTER TABLE IF EXISTS public."Requests table" ALTER COLUMN "ID" SET DEFAULT nextval('"Requests table_ID_seq"'::regclass);""")
		print("Requests table - Created")

	# Tasks table
	if bool(database_request(request="""select * from information_schema.tables where table_name='Tasks table';""", fetch_type="rowcount")):
		print("Tasks table - Exist")
	else:
		database_request(request="""CREATE TABLE public."Tasks table" (
    	id bigint NOT NULL,
    	type character varying(100) NOT NULL,
    	status character varying(12) NOT NULL,
    	owner character varying(100),
    	owner_id bigint NOT NULL,
    	start_date character varying(30) NOT NULL,
    	last_change_date character varying(30) NOT NULL,
    	data text NOT NULL,
    	comment character varying(100),
    	PRIMARY KEY (id)
	);""")
		database_request(request="""CREATE SEQUENCE public."Tasks table_id_seq" CYCLE INCREMENT 1 START 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1;""")
		database_request(request="""ALTER SEQUENCE public."Tasks table_id_seq" OWNED BY public."Tasks table"."id";""")
		database_request(request="""ALTER TABLE IF EXISTS public."Tasks table" ALTER COLUMN "id" SET DEFAULT nextval('"Tasks table_id_seq"'::regclass);""")
		print("Tasks table - Created")

	# Users table
	if bool(database_request(request="""select * from information_schema.tables where table_name='Users table';""", fetch_type="rowcount")):
		print("Users table - Exist")
	else:
		database_request(request="""CREATE TABLE public."Users table" (
    	username character varying NOT NULL,
    	chat_id bigint NOT NULL,
    	domain_username character varying NOT NULL,
		department text,
		notification_app text
	);""")
		print("Users table - Created")

# Service functions
def update_admins_table(access_level, tg_username, chat_id, department) -> None:
	result = database_request(request="""SELECT username, department FROM "Admins table" WHERE chat_id = %s""", data=(chat_id), fetch_type="one")
	if result:
		logging.debug(f"Пользователь {tg_username}:{chat_id} найден среди администраторов")
		if access_level == "User":
			database_request(request="""DELETE FROM "Admins table" WHERE chat_id = %s""", data=(chat_id))
			logging.debug(f"Пользователь {tg_username}:{chat_id} удален из списка администраторов")
		elif access_level == "Admin":
			if (result[0] == tg_username and result[1] == department):
				logging.debug(f"Изменения в списке администраторов для {tg_username}:{chat_id} не требуются")
			else:
				logging.debug(f"Пользователь {tg_username}:{chat_id} обновлен в списку администраторов")
				database_request(request="""UPDATE "Admins table" SET username = %s, department = %s WHERE chat_id = %s""", data=(tg_username, department, chat_id))
	else:
		if access_level == "Admin":
			database_request(request="""INSERT INTO "Admins table" (username, chat_id, department) VALUES (%s,%s,%s)""", data=(tg_username, chat_id, department))
			logging.debug(f"Пользователь {tg_username}:{chat_id} добавлен в список администраторов")

def update_users_table(tg_username: str, chat_id: int, ldap_fullname: str, department: str) -> None:
	result = database_request(request="""SELECT username, domain_username, department FROM "Users table" WHERE chat_id = %s""", data=(chat_id), fetch_type="one")
	if result:
		logging.debug(f"Пользователь {tg_username}:{chat_id} найден в Users")
		if (result[0] == tg_username and result[1] == ldap_fullname, result[2] == department):
			logging.debug(f"Изменения в Users для {tg_username}:{chat_id} не требуются")
		else:
			logging.debug(f"Пользователь {tg_username}:{chat_id} обновлен")
			database_request(request="""UPDATE "Users table" SET username = %s, domain_username = %s, department = %s WHERE chat_id = %s""", data=(tg_username, ldap_fullname, department, chat_id))
	else:
		logging.debug(f"Пользователь {tg_username}:{chat_id} не найден в Users и будет создан")
		database_request(request="""INSERT INTO "Users table" (username, chat_id, domain_username, department, notification_app) VALUES (%s,%s,%s,%s,%s)""", data=(tg_username, chat_id, ldap_fullname, department, "TG"))

# Main requests
@app.post("/ldap_auth")
async def ldap_auth(credentionals: dict, key=Depends(read_key)) -> dict:
	ldap_access, access_level, ldap_username, ldap_fullname, department = ldap_logon(credentionals)
	
	chat_id = credentionals.get("chat_id")
	tg_username = credentionals.get("tg_username")

	if ldap_access and access_level:
		update_admins_table(access_level, tg_username, chat_id, department)
		update_users_table(tg_username, chat_id, ldap_fullname, department)
	
	result = {
		"ldap_access": ldap_access,
		"access_level": access_level,
		"ldap_username": ldap_username,
		"ldap_fullname": ldap_fullname,
		"department": department
	}
	return result

@app.get("/get_ip_info/{ip}")
async def core_get_ip_info(ip: str, key=Depends(read_key)) -> dict | None | str:
	return get_ip_info(ip)

@app.get("/get_inet_access")
async def core_get_inet_access(payload: ip_list_item, key=Depends(read_key)) -> list:
	result_pa = await get_ip_net_info_pa(payload.ip_list)
	result_cp = await get_ip_net_info_cp(payload.ip_list)
	return [result_pa, result_cp]

@app.get("/get_vm_info")
async def core_get_vm_info(payload: vm_name_item, key=Depends(read_key)) -> list | None:
	return get_vm_info(payload.vm_name)


@app.get("/get_last_update")
async def get_last_update(key=Depends(read_key)) -> str:
	logging.debug(f"Запрос get_last_update")
	with open("last_update_info.txt", "r") as update_info_file:
		last_update_data = update_info_file.read()
	logging.debug(f"Ответ на get_last_update: {last_update_data}")	
	return last_update_data

# class Item(BaseModel):
# 	name: str
# 	prop: int
# 	description: str | None = None

# @app.get("/items/{item_id}")
# async def read_item(item_id: int, q: str = None):
# 	return {"item id": item_id, "q": q}

# @app.post("/item/")
# async def create_item(item: Item, key=Depends(read_key)):
	# return(item)

if __name__ == "__main__":
	config_logs = config_read()["app"]["logs"]

	logging.basicConfig(
		level=logging.getLevelName(config_logs["level"].upper()),
		filename=config_logs["file"],
		filemode="a",
		format="%(asctime)s %(levelname)s %(module)s %(funcName)s %(message)s")
	
	logging.info("Started")

	database_init()

	uvicorn.run(app=app, host=config_app["host"], port=config_app["port"])