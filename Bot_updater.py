import os
import platform
import docker
import json
import psycopg2

def main() -> None:
	reset_conf_flag = False
	reset_env_flag = False
	branch = "main"
	
	a = 1
	
	while True:
		
		
		a = 0
		if platform.system() == "Windows":
			os.system('cls')
		else:
			os.system('clear')

		key = input(f"""ITCS VM Portal Bot updater\n
Optinons:\nStream: \033[1m{'\033[92m' if branch == "main" else '\033[93m'}{branch}\033[0m
Reset config.json: \033[1m{'\033[91m' if reset_conf_flag else '\033[92m'}{reset_conf_flag}\033[0m
Reset .env: \033[1m{'\033[91m' if reset_env_flag else '\033[92m'}{reset_env_flag}\033[0m
Choose option:\n1) First phase - Download and unpacked Bot from reposetory\n2) Second phase - Build docker container and upgrade or install bot\n3) Switch reset config flag\n4) Switch reset env flag\n5) Branch select\n6) Exit\n\n\n
Optinon: """)

		match int(key):
			case 1:
				
				github_get = f"wget https://github.com/Sprakis/ITCSvmportal/archive/{branch}.tar.gz"
				os.system(github_get)
				os.system(f"tar --strip-components=1 -xvf {branch}.tar.gz")
				os.system(f"rm {branch}.tar.gz")

				if reset_conf_flag:
					os.system("mv ./Bot/config.json_sample ./Bot/config.json")
					
					docker_client = docker.DockerClient(base_url = 'unix:///var/run/docker.sock')
					
					for network in docker_client.networks.list():
						if network.name == "bridge":
							network_id = network.id
					network = docker_client.networks.get(network_id = network_id)
					host_ip = network.attrs["IPAM"]["Config"][0]["Gateway"]

					with open("./Bot/config.json", 'r') as config_file:
						config = json.load(config_file)
				
					config["databases"]["redis"]["url"] = host_ip
					config["databases"]["psql"]["url"] = host_ip

					with open("./Bot/config.json", 'w') as config_file:
						json.dump(config, config_file, indent=4)

				if reset_env_flag:
					os.system("mv ./Bot/.env_sample ./Bot/.env")

			case 2:
				
				os.chdir("./Bot")
				os.system("docker build -t itcs_vm_portal .")
				os.system("docker run -it -d --env-file .env -v ./:/bot/ --restart=unless-stopped --name itcs_vm_portal_bot itcs_vm_portal")

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
				return 0


if __name__ == "__main__":
	main()