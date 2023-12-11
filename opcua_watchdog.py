from opcua_client import connect_opcua, write_tag
from create_logger import setup_logger
from data_encrypt import DataEncryptor
import asyncio
from config_handler import ConfigHandler


######################
# Config files
config_manager = ConfigHandler()
opcua_alarm_config = config_manager.opcua_server_alarm_config

# Config data
OPCUA_SERVER_CRED_PATH:str = opcua_alarm_config["opcua_server_cred_path"]
OPCUA_SERVER_WINDOWS_ENV_KEY_NAME:str = opcua_alarm_config["environment_variables"]["opcua"]

WATCHDOG_INTERVAL = 10
######################

logger = setup_logger(__name__)

class Watchdog:
    """
    Watchdog class to monitor and maintain OPC UA server connections.
    """
    def __init__(self, url: str, username: str, password: str):
        self.url = url
        self.username = username
        self.password = password
        self.client = None


    async def configure_servers(self):
        """
        Configure servers based on encrypted configuration.
        """
        data_encrypt = DataEncryptor()
        opcua_config = data_encrypt.encrypt_credentials(OPCUA_SERVER_CRED_PATH, OPCUA_SERVER_WINDOWS_ENV_KEY_NAME)

        if not opcua_config:
            logger.error("Could not read OPC UA config file")
            raise FileNotFoundError("Could not read OPC UA config file")

        tasks = [self.watchdog(server["address"], server["username"], server["password"]) for server in opcua_config["servers"]]
        await asyncio.gather(*tasks)


    async def watchdog(self, url: str, username: str, password: str):
        """
        Monitor and maintain a connection to an OPC UA server.
        """
        try:
            client = await connect_opcua(url, username, password)
            async with client:
                while True:
                    await client.check_connection()
                    await write_tag(client, "placeholder", 1)
                    await asyncio.sleep(WATCHDOG_INTERVAL)
        except Exception as e:
            logger.error(f"Error in watchdog for {url}: {e}")


async def main_watchdog(url: str, username: str, password: str):
    """
    Main function to initiate the Watchdog.
    """
    watchdog = Watchdog(url, username, password)
    print("Starting watchdog")
    #await watchdog.configure_servers()


if __name__ == "__main__":
    asyncio.run(main_watchdog("url", "username", "password"))






