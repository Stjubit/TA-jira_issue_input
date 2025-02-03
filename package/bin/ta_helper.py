"""
Helper functions used by multiple inputs
"""

import import_declare_test
import logging
import splunklib.client
import requests

from solnlib import conf_manager, log, utils
from solnlib.modular_input import checkpointer
from splunktaucclib.rest_handler import util as ucc_rest_util


def initalize_logger(
    input_type: str, input_name: str, settings_conf_name: str, session_key
) -> logging.Logger:
    """
    This function initializes a logging.Logger object for Splunk using
    the solnlib library.
    """
    logger = log.Logs().get_logger(f"{import_declare_test.ADDON_NAME}_{input_type}_{input_name}")

    # fetch log level from TA configuration and set it for logger
    log_level = conf_manager.get_log_level(
        logger=logger,
        session_key=session_key,
        app_name=import_declare_test.ADDON_NAME,
        conf_name=settings_conf_name,
    )
    logger.setLevel(log_level)

    return logger


def get_account_details(
    logger: logging.Logger, session_key: str, account_conf_name: str, account_name: str
) -> dict:
    """
    This function reads account configuration from Splunk using solnlib and
    returns it as dict.

    Returns None if account configuration could not be read.
    """
    cfm = conf_manager.ConfManager(
        session_key=session_key,
        app=import_declare_test.ADDON_NAME,
        realm=f"__REST_CREDENTIAL__#{import_declare_test.ADDON_NAME}#configs/conf-{account_conf_name}",
    )
    try:
        account_conf_file = cfm.get_conf(account_conf_name)
        return account_conf_file.get(account_name)
    except Exception as ex:
        log.log_exception(
            logger,
            ex,
            "Account Read Error",
            msg_before=f"Unable to read account {account_name} in configuration file {account_conf_name}",
        )
        return None


def initialize_splunklib_client(server_uri: str, session_key: str) -> splunklib.client.Service:
    """
    This function initializes a splunklib client
    """
    dscheme, dhost, dport = utils.extract_http_scheme_host_port(server_uri)
    splunklib_client = splunklib.client.connect(
        host=dhost,
        port=dport,
        scheme=dscheme,
        app=import_declare_test.ADDON_NAME,
        token=session_key,
    )

    return splunklib_client


def initialize_checkpointer(
    logger: logging.Logger, server_uri: str, session_key: str
) -> checkpointer.KVStoreCheckpointer:
    """
    This function initializes a KV Store Checkpointer.

    Returns None if KVStore Collection can not be read.
    """
    dscheme, dhost, dport = utils.extract_http_scheme_host_port(server_uri)
    collection_name = f"{import_declare_test.ADDON_NAME.replace('-', '_')}_checkpointer"

    try:
        checkpoint = checkpointer.KVStoreCheckpointer(
            collection_name,
            session_key,
            import_declare_test.ADDON_NAME,
            scheme=dscheme,
            host=dhost,
            port=dport,
        )
        return checkpoint
    except Exception as ex:
        log.log_exception(
            logger,
            ex,
            "KVStore Collection Read Error",
            msg_before=f"Unable to read KVStore collection {collection_name}",
        )
        return None


def initialize_requests_proxy(
    logger: logging.Logger, session_key: str, settings_conf_name: str, proxy_stanza: str
) -> dict:
    """
    This function reads proxy configuration from settings and returns
    a Python requests proxy configuration dict or None if proxy config
    can't be read
    """
    # read proxy settings from conf file
    try:
        proxy_config = conf_manager.get_proxy_dict(
            logger, session_key, import_declare_test.ADDON_NAME, settings_conf_name, proxy_stanza
        )
    except Exception as ex:
        log.log_exception(
            logger,
            ex,
            "Proxy Configuration Error",
            msg_before="Unable to read proxy configuration",
            log_level=logging.INFO,
        )
        return {}

    logger.debug(f"Proxy configuration from .conf: {proxy_config}")

    # check if proxy has been enabled in settings
    if (
        "proxy_enabled" not in proxy_config
        or not proxy_config["proxy_enabled"]
        or str(proxy_config["proxy_enabled"]).lower() in ["no", "false", "0"]
    ):
        return {}

    # map config to proxy URI
    proxy_uri = ucc_rest_util.get_proxy_uri(proxy_config)

    # map proxy URI to Python requests proxy configuration
    if proxy_uri:
        logger.debug(f"Proxy URI: {proxy_uri}")
        return {"http": proxy_uri, "https": proxy_uri}

    return {}


def initialize_requests_session(
    logger: logging.Logger,
    verify: bool = False,
    use_proxy: bool = False,
    session_key: str = "",
    settings_conf_name: str = "",
    proxy_stanza: str = "",
) -> requests.Session:
    """
    This function initializes a Python requests session with proxy
    settings if it has been enabled and configured correctly.
    """
    session = requests.Session()
    session.verify = verify

    # initialize proxy
    if use_proxy:
        proxy_dict = initialize_requests_proxy(
            logger, session_key, settings_conf_name, proxy_stanza
        )

        if proxy_dict:
            logger.info("Enabled proxy for HTTP requests")
            session.proxies = proxy_dict

    return session
