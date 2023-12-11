from asyncua import Client, ua, Node

from create_logger import setup_logger

##############################
CLIENT_TIMEOUT = 10
##############################

logger = setup_logger(__name__)


async def connect_opcua(url: str, username: str, password: str):

    """
    Connect to an OPC UA server.

    :param url: Server URL
    :param username: username
    :param password: password
    :return: Client object if connected, None otherwise
    """

    client = Client(url=url, timeout=CLIENT_TIMEOUT, watchdog_intervall=10.0)

    try:
        logger.info(f"Connecting to OPC UA server at {url}")

        client.set_user(username)
        client.set_password(password)

        await client.connect()

        logger.info("Successfully connected to OPC UA server.")

    except ua.uaerrors.BadUserAccessDenied as exception:
        logger.error(f"BadUserAccessDenied: {exception}")
        raise exception

    except ua.uaerrors.BadSessionNotActivated as exception:
        logger.error(f"Session activation error: {exception}")
        raise exception

    except ua.uaerrors.BadIdentityTokenRejected as exception:
        logger.error(f"Identity token rejected. Check username and password.: {exception}")
        raise exception

    except ua.uaerrors.BadIdentityTokenInvalid as exception:
        logger.error(f"Bad Identity token invalid. Check username and password.: {exception}")
        raise exception

    except ConnectionError as exception:
        logger.error(f"Connection error: Please check the server url. Or other connection properties: {exception}")
        raise exception

    except ua.UaError as exception:
        logger.error(f"General OPCUA error {exception}")
        raise exception

    except Exception as exception:
        logger.error(f"Error in connection: {exception} Type: {type(exception)}")
        raise exception

    return client


async def write_tag(client: Client, tag_name, tag_value):
    """
    Write a value to a specific tag within the client.

    :param client: The client object
    :param tag_name: The tag name to write to
    :param tag_value: The value to write
    :return: A tuple containing result message and fault flag
    """
    result = "Tag not found"
    fault = False

    try:
        node_id: Node = ua.NodeId.from_string(tag_name)
        node: Node = client.get_node(node_id)

    except Exception as exeption:
        logger.error(exeption)
        await client.disconnect()
        fault = True
        return result, fault

    # Write the value to the node
    if node_id is not None:
        data_value = None
        try:

            # Define conversion functions
            def to_bool(value):
                if isinstance(value, bool):
                    return value
                elif isinstance(value, str):
                    return value.lower() == "true"
                else:
                    raise ValueError("Invalid type for conversion to bool")


            def to_float(value):
                return float(value)

            def to_int(value):
                return int(value)

            # Define data type to conversion function mapping
            conversion_map = {
                ua.VariantType.Boolean: to_bool,
                ua.VariantType.Float: to_float,
                ua.VariantType.Int16: to_int,
                ua.VariantType.Int32: to_int,
                ua.VariantType.Int64: to_int,
                ua.VariantType.UInt16: to_int,
                ua.VariantType.UInt32: to_int,
                ua.VariantType.UInt64: to_int,
            }

            # Convert tag value to data value
            data_type = await node.read_data_type_as_variant_type()
            if data_type in conversion_map:
                conversion_func = conversion_map[data_type]
                if isinstance(tag_value, str) or isinstance(tag_value, int):
                    tag_value = conversion_func(tag_value)
                if isinstance(tag_value, bool) or isinstance(tag_value, float) or isinstance(tag_value, int):
                    data_value = ua.DataValue(ua.Variant(tag_value, data_type))
            elif data_type == ua.VariantType.String:
                if isinstance(tag_value, str):
                    data_value = ua.DataValue(ua.Variant(tag_value, data_type))

            result = "Tag found but no correct tag value"
        except Exception as exeption:
            await client.disconnect()
            fault = True
            logger.error(f"Error converting data type to ua.Variant: {exeption}")
            return result, fault

        if data_value is not None:

            try:
                await node.write_value(data_value)
                result = "Success finding tag and writing value"
            except Exception as exeption:
                fault = True
                await client.disconnect()
                logger.error(f"Error writing value to tag: {tag_name},{tag_value}, from {node_id}. {exeption}")
                return result, fault

    return result, fault
