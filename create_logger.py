"""
This file contains function to easy create programming loggers and alarm loggers.
version: 1.0.0 Inital commit by Roberts balulis
"""
__version__ = "1.0.0"


import logging
import os
import sys

def setup_logger(logger_name):

    """
    Creates and configures a logging instance for the specified module.

    This function creates a logger with the provided logger_name, sets its level to DEBUG,
    and associates it with a file handler that writes to a log file. The log file is stored
    in a 'logs' directory or 'alarms' directory depending on the logger_name.

    This will create a logger that writes messages to the 'module_name.log' file in the 'logs'
    directory. If the logger_name is 'alarms', it will write to the 'alarms' directory instead.

    Parameters
    ----------
    logger_name - The name of the logger. This will be the name of the module where the
    logger is used.

    Usage
    ----------
    logger = setup_logger(__name__)
    """

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)

    if getattr(sys, 'frozen', False): # If the program is running in a PyInstaller bundle
        app_path = sys._MEIPASS
    else:
        app_path = os.path.dirname(os.path.abspath(__file__)) # Else the program is running in a normal Python environment
        parent_dir = os.path.dirname(app_path)

    alarms = "alarms"
    log_folder = "logs"

    if logger_name  != "alarms":

        log_dir = os.path.abspath(os.path.join(parent_dir, log_folder))
        try:
            os.makedirs(log_dir, exist_ok=True)
        except PermissionError:
            raise PermissionError("There was a problem creating the logs directory. Please check your permissions and try again.")

    else:
        log_dir = os.path.abspath(os.path.join(parent_dir, alarms))
        try:
            os.makedirs(log_dir, exist_ok=True)
        except PermissionError:
            raise PermissionError("There was a problem creating the alarms directory. Please check your permissions and try again.")

    log_file = os.path.join(log_dir, f"{logger_name}.log")
    formatter = logging.Formatter('%(asctime)s|%(levelname)s|%(name)s|%(message)s', datefmt='%Y:%m:%d %H:%M:%S')

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    logger.addHandler(file_handler)

    return logger