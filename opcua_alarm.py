"""
This module is used to monitor alarms from OPC UA servers.
It reads multiple OPC UA server config files and starts a subscription to each server.
If the send_sms flag is set to True, it will send an SMS message to the specified phone number else it will log the message.

It has been tested and works with a Siemens PLC.

version: 1.0.0 Inital commit by Roberts balulis
"""
__version__ = "1.0.0"

import asyncio
from datetime import datetime

from asyncua import ua, Client
import logging
from queue import Queue
from threading import Thread
import json

try:
    from create_logger import setup_logger
    from opcua_client import connect_opcua
    from data_encrypt import DataEncryptor
    from config_handler import ConfigHandler
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
except ImportError:
    print(f"Some modules was not found in. Please make sure it is in the same directory as this script.")

try:
    from sms_sender import send_sms
except ImportError:
    print(f"The sms_sender module was not found. You will not be able to send SMS messages.")

####################################

# Logging
logger_programming = setup_logger('opcua_prog_alarm')
logger_opcua_alarm = setup_logger("opcua_alarms")

# Config files
config_manager = ConfigHandler()
phone_book:dict = config_manager.phone_book
opcua_alarm_config = config_manager.opcua_server_alarm_config

# Config data
SEND_SMS:bool = opcua_alarm_config["config"]["send_sms"]
ALARM_CONDITION_TYPE:str = opcua_alarm_config["config"]["alarm_condition_type"]
SERVER_NODE_IDENTIFIER:int = opcua_alarm_config["config"]["server_node_identifier"]
SERVER_NODE_NAMESPACE_INDEX:int = opcua_alarm_config["config"]["server_node_namespace_index"]
DAY_TRANSLATION:dict = opcua_alarm_config["day_translation"]
OPCUA_SERVER_CRED_PATH:str = opcua_alarm_config["opcua_server_cred_path"]
OPCUA_SERVER_WINDOWS_ENV_KEY_NAME:str = opcua_alarm_config["environment_variables"]["opcua"]
SMS_MESSAGE:str = opcua_alarm_config["config"]["messege"]
####################################



executor = ThreadPoolExecutor(max_workers=1)

sms_queue = Queue()

def sms_worker():
    while True:
        phone_number, message = sms_queue.get()
        send_sms(phone_number, message)
        sms_queue.task_done()


# Start the SMS worker thread.
Thread(target=sms_worker, daemon=True).start()


async def subscribe_to_server(adresses: str, username: str, password: str):
    """
    Parameters
    ----------
    adresses - The address of the OPC UA server
    username - The username to use when connecting to the OPC UA server
    password - The password to use when connecting to the OPC UA server
    """
    subscribing_params = ua.CreateSubscriptionParameters()
    subscribing_params.RequestedPublishingInterval = 1000
    subscribing_params.RequestedLifetimeCount = 400
    subscribing_params.RequestedMaxKeepAliveCount = 100
    subscribing_params.MaxNotificationsPerPublish = 0
    subscribing_params.PublishingEnabled = True
    subscribing_params.Priority = 0

    client:Client = None
    sub = None
    while True:

        try:
            if client is None:
                client = await connect_opcua(adresses, username, password)

            async with client as client:
                await client.check_connection()

                conditionType = client.get_node("ns=0;i=2782")
                alarmConditionType = client.get_node("ns=0;i=2915")
                server_node = client.get_node(ua.NodeId(Identifier=2253,
                                                    NodeIdType=ua.NodeIdType.Numeric, NamespaceIndex=0))

                msclt = SubHandler(adresses)
                sub = await client.create_subscription(subscribing_params, msclt)
                handle = await sub.subscribe_alarms_and_conditions(server_node, alarmConditionType)
                await conditionType.call_method("0:ConditionRefresh", ua.Variant(sub.subscription_id, ua.VariantType.UInt32))

                logger_programming.info("Made a new subscription")

                while True:
                    try:
                        await asyncio.sleep(1)
                        await client.check_connection()

                        if not client.uaclient._publish_task or client.uaclient._publish_task.done():
                            logger_programming('Detected dead publish task, rebuilding...')
                            sub = await client.create_subscription(subscribing_params, msclt)
                            handle = await sub.subscribe_alarms_and_conditions(server_node, alarmConditionType)
                            logger_programming("Subscription rebuilt successfully.")

                    except (ConnectionError, ua.UaError) as e:
                        logger_programming.warning(f"{e} Reconnecting in 30 seconds")
                        if client is not None:
                            await client.delete_subscriptions(sub)
                            await client.disconnect()
                            client = None
                        await asyncio.sleep(30)

        except (ConnectionError, ua.UaError) as e:
            logger_programming.warning(f"{e} Reconnecting in 30 seconds")
            if client is not None and sub is not None:
                try:
                    await client.delete_subscriptions(sub)
                    await client.disconnect()
                except:
                    pass
                client = None
            await asyncio.sleep(30)

        except Exception as e:
            logger_programming.error(f"Error connecting or subscribing to server {adresses}: {e}")
            if client is not None and sub is not None:
                try:
                    await client.delete_subscriptions(sub)
                    await client.disconnect()
                except:
                    pass
            client = None
            await asyncio.sleep(30)


class SubHandler:
    """
    Handles the events received from the OPC UA server, and what to do with them.
    """

    def __init__(self, address: str):
        self.address = address
        self.recurring_alarms = set()

    def status_change_notification(self, status: ua.StatusChangeNotification):
        """
        Called when a status change notification is received from the server.
        """
        # Handle the status change event. This could be logging the change, raising an alert, etc.
        logger_opcua_alarm.info(status)


    async def event_notification(self, event):
        """
        This function is called when an event is received from the OPC UA server.
        and saves it to a log file.
        returns: the event message
        """

        opcua_alarm_message = {
            "New event received from": self.address
        }

        attributes_to_check = [
            "Message", "Time", "Severity", "SuppressedOrShelved",
            "AckedState", "ConditionClassId", "NodeId", "Quality", "Retain",
            "ActiveState", "EnabledState"
        ]

        for attribute in attributes_to_check:
            if hasattr(event, attribute):
                value = getattr(event, attribute)
                if hasattr(value, "Text"):
                    value = value.Text
                opcua_alarm_message[attribute] = value

        if hasattr(event, "NodeId") and hasattr(event.NodeId, "Identifier"):
            opcua_alarm_message["Identifier"] = str(event.NodeId.Identifier)


        if opcua_alarm_message["Message"]:
            if opcua_alarm_message["Message"] in self.recurring_alarms:
                if opcua_alarm_message["AckedState"] == "Unacknowledged":
                    return
                elif opcua_alarm_message["AckedState"] == "Acknowledged":
                    self.recurring_alarms.remove(opcua_alarm_message["Message"])
                    return
            else:
                self.recurring_alarms.add(opcua_alarm_message["Message"])

        if SEND_SMS and opcua_alarm_message["ActiveState"] == "Active":
            await self.user_notification(opcua_alarm_message["Message"], opcua_alarm_message['Severity'])
            logger_opcua_alarm.info(f"New event received from {self.address}: {opcua_alarm_message}")
        else:
            if opcua_alarm_message["ActiveState"] == "Active":
                logger_opcua_alarm.info(f"New event received from {self.address}: {opcua_alarm_message}")


    async def user_notification(self, opcua_alarm_message:str, severity:int):
        tasks = []
        current_time = datetime.now().time()
        current_day = datetime.now().strftime('%A')
        translated_day = DAY_TRANSLATION[current_day]

        for user in phone_book:
            if user.get('Active') == 'Yes':
                user_settings = user.get('timeSettings', [])

                for setting in user_settings:
                    if translated_day in setting.get('days', []):
                        start_time = datetime.strptime(setting.get('startTime', '00:00'), '%H:%M').time()
                        end_time = datetime.strptime(setting.get('endTime', '00:00'), '%H:%M').time()

                        if start_time <= current_time <= end_time:
                            lowest_severity = int(setting.get('lowestSeverity', 0))
                            highest_severity = int(setting.get('highestSeverity', 100))

                            if min(lowest_severity, highest_severity) <= severity <= max(lowest_severity, highest_severity):

                                phone_number = user.get('phone_number')
                                name = user.get('Name')
                                message = f"{SMS_MESSAGE} {opcua_alarm_message}, allvarlighetsgrad: {severity}"

                                word_filter = setting.get('wordFilter', '')

                                if word_filter:
                                    include_words, exclude_words = parse_filter(word_filter)
                                    alarm_message_lower = opcua_alarm_message.lower()

                                    if (any(word in alarm_message_lower for word in include_words) and
                                        not any(word in alarm_message_lower for word in exclude_words)):

                                        sms_queue.put((phone_number, message))
                                        logger_opcua_alarm.info(f"Sent SMS to {name}")
                                        break

                                else:
                                    sms_queue.put((phone_number, message))
                                    logger_opcua_alarm.info(f"Sent SMS to {name}")
                                    break


def parse_filter(filter_str):
    # Split the filter string into include and exclude lists
    parts = filter_str.split('.')
    include_words = []
    exclude_words = []

    for part in parts:
        if part.startswith('"') and part.endswith('"'):
            include_words.append(part[1:-1].lower())  # Add phrase without quotes
        elif part.startswith('-'):
            exclude_words.append(part[1:].lower())  # Add word without minus
        else:
            include_words.append(part.lower())

    return include_words, exclude_words


async def monitor_alarms():
    """
    Reads the OPC UA server config file and starts a subscription to each server.
    """

    data_encrypt = DataEncryptor()
    opcua_config = data_encrypt.encrypt_credentials(OPCUA_SERVER_CRED_PATH, OPCUA_SERVER_WINDOWS_ENV_KEY_NAME)

    if opcua_config is None:
        logger_programming.error("Could not read OPC UA config file")
        raise FileNotFoundError("Could not read OPC UA config file")

    tasks = []

    for server in opcua_config["servers"]:
        encrypted_username = server["username"]
        encrypted_password = server["password"]
        encrypted_address = server["address"]

        tasks.append(asyncio.create_task(subscribe_to_server(encrypted_address,
                                                            encrypted_username, encrypted_password)))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(monitor_alarms())

