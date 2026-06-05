import os
import platform
import docker
import json

def check_versions(container_name: str) -> str:
	docker_client = docker.DockerClient(base_url = 'unix:///var/run/docker.sock')
	modules = ["itcs_vm_portal_core",
			"itcs_vm_portal_telegram_bot"]
	for container in docker_client.containers.list(all = True):
		if container.name in modules:
			if container_name in container.name:
				return container.image.tags[0].split(":")[1]
	return "Not installed"

def main() -> None:
	reset_conf_flag = False
	reset_env_flag = False
	branch = "main"
	msg = "Hello"
	
	while True:
		
		
		if platform.system() == "Windows":
			os.system('cls')
		else:
			os.system('clear')

		print(f"Status: {msg}")

		key = input(f"""ITCS VM Portal Bot updater\n\nModules:\nCore:{check_versions("core")}\nTelegram BOT:{check_versions("telegram_bot")}\n
Options:\nStream: \033[1m{'\033[92m' if branch == "main" else '\033[93m'}{branch}\033[0m
Reset config.json: \033[1m{'\033[91m' if reset_conf_flag else '\033[92m'}{reset_conf_flag}\033[0m
Reset .env: \033[1m{'\033[91m' if reset_env_flag else '\033[92m'}{reset_env_flag}\033[0m
Choose option:\n1) First phase - Download and unpacked Bot from repository\n2) Second phase - Build docker container and upgrade or install bot\n3) Switch reset config flag\n4) Switch reset env flag\n5) Branch select\n6) Delete backups containers\n7) Exit\n\n\n
Option: """)

		match int(key):
			case 1:
				
				# github_get = f"wget https://github.com/Sprakis/ITCSvmportal/archive/{branch}.tar.gz"
				# os.system(github_get)
				# os.system(f"tar --strip-components=1 -xvf {branch}.tar.gz")
				# os.system(f"rm {branch}.tar.gz")

				if reset_conf_flag:
					os.system("mv ./config.json_sample ./config.json")

				if reset_env_flag:
					os.system("mv .env_sample .env")

				msg = "Bot downloaded and unpacked"

			case 2:

				docker_client = docker.DockerClient(base_url = 'unix:///var/run/docker.sock')
				
				for network in docker_client.networks.list():
					if network.name == "bridge":
						network_id = network.id
				
				network = docker_client.networks.get(network_id = network_id)
				host_ip = network.attrs["IPAM"]["Config"][0]["Gateway"]

				with open("./config.json", 'r') as config_file:
					config = json.load(config_file)
			
				config["databases"]["redis"]["url"] = host_ip
				config["databases"]["psql"]["url"] = host_ip
				config["app"]["internal_access"] = host_ip

				with open("./config.json", 'w') as config_file:
					json.dump(config, config_file, indent=4)
				

				os.system("cp requiriments.txt ./app/")
				os.system("cp config.json ./app/")

				try:
					os.system("cp requiriments.txt ./telegram_bot/")
					os.system("cp config.json ./telegram_bot/")
				except:
					pass

				# Core
				print("Build CORE module")
				os.chdir("./app")

				with open("./version.txt", "r") as version_file:
					version_core = version_file.read()

				os.system(f"docker build -t itcs_vm_portal_core:{version_core} .")
				
				# TG bot
				try:
					print("Build TIMERMAN module")
					os.chdir("../telegram_bot")

					os.system("docker build -t itcs_vmp_timerman -f ./modules/Dockerfile_timerman .")


					print("Build TELEGRAM BOT module")

					with open("./version.txt", "r") as version_file:
						version_telegram_bot = version_file.read()

					os.system(f"docker build -t itcs_vm_portal_telegram_bot:{version_telegram_bot} .")
				except:
					pass

				docker_client = docker.DockerClient(base_url = 'unix:///var/run/docker.sock')

				print("Delete backups")
				for container in docker_client.containers.list(all = True):
					if container.name == "itcs_vm_portal_core_backup":
						container.remove(v = True)
					if container.name == "itcs_vmpb_timerman_backup":
						container.remove(v = True)
					if container.name == "itcs_vm_portal_telegram_bot_backup":
						container.remove(v = True) 

				msg = "Backup containers successfully deleted"

				print("Backups containers")

				for container in docker_client.containers.list(all = True):
					if container.name == "itcs_vm_portal_core":
						container.stop()
						container.rename(name = "itcs_vm_portal_core_backup")
					if container.name == "itcs_vm_portal_telegram_bot":
						container.stop()
						container.rename(name = "itcs_vm_portal_telegram_bot_backup")
					if container.name == "itcs_vmpb_timerman":
						container.stop()
						container.rename(name = "itcs_vmpb_timerman_backup")

				os.chdir("..")

				print("Start core module")
				app_port = config["app"]["port"]
				os.system(f"docker run -it -d --env-file .env -v ./app/:/app/ -v /var/log/ITCS_vmpb/:/var/log/ITCS_vmpb/ --restart=unless-stopped --name itcs_vm_portal_core -p {app_port}:{app_port} itcs_vm_portal_core:{version_core}")

				print("Start timerman module")
				os.system("docker run -it -d --env-file .env -v ./telegram_bot/:/bot/ -v /var/log/ITCS_vmpb/:/var/log/ITCS_vmpb/ --restart=unless-stopped --name itcs_vmpb_timerman itcs_vmp_timerman")
					
				print("Start telegram bot")
				os.system(f"docker run -it -d --env-file .env -v ./telegram_bot/:/bot/ -v /var/log/ITCS_vmpb/:/var/log/ITCS_vmpb/ --restart=unless-stopped --name itcs_vm_portal_telegram_bot itcs_vm_portal_telegram_bot:{version_telegram_bot}")
				
				os.system("rm ./app/requiriments.txt")

				try:
					os.system("rm ./telegram_bot/requiriments.txt")
				except:
					pass
				
				msg = "The bot has been successfully installed and launched"

			case 3:
				if reset_conf_flag:
					reset_conf_flag = False
				else:
					reset_conf_flag = True

			case 4:
				if reset_env_flag:
					reset_env_flag = False
				else:
					reset_env_flag = True
			
			case 5:
				branch = input("Please input branch name: ")
			
			case 6:
				print("Delete backups")
				docker_client = docker.DockerClient(base_url = 'unix:///var/run/docker.sock')
				for container in docker_client.containers.list(all = True):
					if container.name == "itcs_vm_portal_core_backup":
						container.remove(v = True)
					if container.name == "itcs_vmpb_timerman_backup":
						container.remove(v = True)
					if container.name == "itcs_vm_portal_telegram_bot_backup":
						container.remove(v = True) 

				msg = "Backup containers successfully deleted"

			case 7:
				return 0


if __name__ == "__main__":
	main()