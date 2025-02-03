# encoding = utf-8
import sys
import base64
import json
import re
import logging

import ta_helper

from splunklib import modularinput as smi
from splunktaucclib.rest_handler.error import RestError
from solnlib import log

from requests.exceptions import RequestException
from datetime import datetime, timedelta, timezone


def _parse_datetime(logger: logging.Logger, datetimestr: str):
    """
    This function is used to validate and parse a given Jira datetime string
    """
    try:
        return datetime.strptime(datetimestr, "%Y-%m-%d %H:%M")
    except ValueError:
        logger.warning(
            "The provided last updated start time does not match the required format '%Y-%m-%d %H:%M'"
        )
        return None


def validate_input(definition: smi.ValidationDefinition):
    # validate available input parameters
    jql = definition.parameters.get("jql", None)
    if not jql:
        raise RestError(400, "You have to enter a valid JQL")

    issue_fields = definition.parameters.get("issue_fields", None)
    if not issue_fields:
        raise RestError(400, "You have to enter Jira Issue fields to collect")

    # check if issue field list is valid
    for field in issue_fields.split(","):
        if len(field.strip()) == 0:
            raise RestError(400, "You have entered an invalid comma-separated list of issue fields")

    return True


def stream_events(inputs: smi.InputDefinition, event_writer: smi.EventWriter):
    """
    This function queries the Jira REST API to collect Jira issue data
    and indexes them in Splunk accordingly
    """
    for input_name, input_item in inputs.inputs.items():
        session_key = inputs.metadata["session_key"]
        normalized_input_name = input_name.split("/")[-1]

        # initialize logger
        logger = ta_helper.initalize_logger(
            "jira-issue",
            normalized_input_name,
            "ta_jira_issue_input_settings",
            session_key,
        )
        log.modular_input_start(logger, normalized_input_name)

        # fetch input configuration
        opt_jql = input_item["jql"] if "jql" in input_item else None
        opt_last_updated_start_time = (
            input_item["last_updated_start_time"]
            if "last_updated_start_time" in input_item
            else None
        )
        opt_issue_fields = input_item["issue_fields"] if "issue_fields" in input_item else None
        opt_expand_fields = (
            input_item["expand_fields"] if "expand_fields" in input_item else None
        )  # optional parameter
        opt_service_account = (
            input_item["service_account"] if "service_account" in input_item else None
        )

        # validate input options
        if not opt_jql or not opt_issue_fields or not opt_service_account:
            logger.critical(
                "The input {} is not configured properly. Please double-check the input configuration!".format(
                    normalized_input_name
                )
            )
            log.modular_input_end(logger, normalized_input_name)
            sys.exit(1)

        # fetch account information
        jira_account = ta_helper.get_account_details(
            logger, session_key, "ta_jira_issue_input_account", opt_service_account
        )
        opt_jira_server = jira_account["jira_server"] if "jira_server" in jira_account else None
        opt_username = jira_account["username"] if "username" in jira_account else None
        opt_password = jira_account["password"] if "password" in jira_account else None
        opt_verify_cert = (
            True
            if "verify_jira_server_certificate" in jira_account
            and jira_account["verify_jira_server_certificate"]
            and str(jira_account["verify_jira_server_certificate"]).lower()
            not in ["no", "false", "0"]
            else False
        )

        logger.debug(f"SSL certificate verification: {opt_verify_cert}")

        # validate global account
        if not opt_jira_server or not opt_username or not opt_password:
            logger.critical(
                "The global account with ID {} is not configured properly. Please double-check the account configuration!".format(
                    opt_service_account
                )
            )
            log.modular_input_end(logger, normalized_input_name)
            sys.exit(1)

        # initialize KVStore checkpointer
        kv_checkpoint = ta_helper.initialize_checkpointer(
            logger, inputs.metadata["server_uri"], session_key
        )

        checkpoint_value = kv_checkpoint.get(normalized_input_name)

        if checkpoint_value is None:
            logger.info(
                "The checkpoint for input {} does not yet exist! Initializing checkpoint ...".format(
                    normalized_input_name
                )
            )

            default_last_updated_start_time = datetime.now(timezone.utc) - timedelta(7)
            checkpoint_value = int(default_last_updated_start_time.timestamp() * 1000)

            if opt_last_updated_start_time:
                logger.info(
                    "A last updated start time has been configured for the input! Validating timestamp ..."
                )

                last_updated_start_time = _parse_datetime(logger, opt_last_updated_start_time)
                if last_updated_start_time is not None:
                    # set checkpoint to last_updated_start_time
                    logger.info("The provided last updated start time is valid!")
                    checkpoint_value = int(last_updated_start_time.timestamp() * 1000)
                else:
                    # use the default last updated start time
                    logger.warning(
                        "The provided last updated start time is invalid - the checkpoint will be initialized with default values!"
                    )
            else:
                logger.info(
                    "The input started without a last updated start time setting - the checkpoint will be initialized with default values!"
                )

            logger.info(
                "Initializing checkpoint with value '{}' ({})".format(
                    checkpoint_value,
                    datetime.fromtimestamp(checkpoint_value / 1000).strftime("%Y-%m-%d %H:%M UTC"),
                )
            )

            try:
                kv_checkpoint.update(normalized_input_name, checkpoint_value)
                logger.info("Successfully initialized checkpoint!")
            except Exception as exc:
                log.log_exception(
                    logger,
                    exc,
                    "Checkpoint Initialization Error",
                    msg_before="Unable to initialize checkpoint - the input can't be started!",
                )
                log.modular_input_end(logger, normalized_input_name)
                sys.exit(1)

        # split JQL to check for updated field
        jql_parts = [part.lower() for part in re.split("[^a-zA-Z]", opt_jql)]
        logger.debug("JQL splitted parts: {}".format(jql_parts))

        # verify if checkpoint should be used for data collection or not
        if ("updated" in jql_parts) or ("updateddate" in jql_parts):
            logger.info(
                "Starting input {} without using the checkpoint, because an updated field has been set in the JQL filter!".format(
                    normalized_input_name
                )
            )
        else:
            logger.info(
                "Starting input {} with checkpoint value {} ({})!".format(
                    normalized_input_name,
                    checkpoint_value,
                    datetime.fromtimestamp(checkpoint_value / 1000).strftime(
                        "%Y-%m-%d %H:%M.%f UTC"
                    ),
                )
            )

            # add checkpoint value to JQL
            opt_jql = "updated > {} AND {}".format(checkpoint_value, str(opt_jql).strip())
            logger.debug("Updated JQL: {}".format(opt_jql))

        # API pagination
        # maxResults is not used, because every Jira server can have different limits
        # total is not used, because it is not included in the response for expensive searches
        # last_updated_time gets initialized with checkpoint value
        start_at = 0
        new_issues_fetched = True
        num_issues_indexed = 0
        last_updated_time = datetime.fromtimestamp(checkpoint_value / 1000, tz=timezone.utc)

        while new_issues_fetched:
            # get Jira issues via REST API
            logger.info(
                "Sending request to Jira REST API (startAt={}, input={})".format(
                    start_at, normalized_input_name
                )
            )

            request_params = {
                "jql": opt_jql,
                "fields": "updated,{}".format(opt_issue_fields.replace(" ", "")),
                "validateQuery": "true",
                "startAt": start_at,
            }

            if opt_expand_fields:
                request_params["expand"] = opt_expand_fields.replace(" ", "")

            logger.debug("Request parameters for Jira REST API: {}".format(request_params))

            request_headers = {
                "Authorization": "Basic {}".format(
                    base64.b64encode(
                        "{}:{}".format(opt_username, opt_password).encode("ascii")
                    ).decode("ascii")
                )
            }

            # initialize request session
            session = ta_helper.initialize_requests_session(
                logger,
                opt_verify_cert,
                True,
                session_key,
                "ta_jira_issue_input_settings",
                "custom_proxy",
            )

            try:
                response = session.get(
                    url="https://{}/rest/api/2/search".format(opt_jira_server),
                    params=request_params,
                    headers=request_headers,
                )
            except RequestException as exc:
                log.log_exception(
                    logger,
                    exc,
                    "HTTP Request Error",
                    msg_before=f"Unable to send request to Jira REST API for input {normalized_input_name}",
                )
                log.modular_input_end(logger, normalized_input_name)
                sys.exit(1)

            if not response.ok:
                logger.critical(
                    "The Jira REST API returned an error when fetching issues for input {}: {}".format(
                        normalized_input_name, response.text
                    )
                )
                log.modular_input_end(logger, normalized_input_name)
                sys.exit(1)

            # check if new issues have been fetched (otherwise all pages have been queried)
            try:
                response_data = response.json()
            except RequestException as exc:
                log.log_exception(
                    logger,
                    exc,
                    "Jira API Error",
                    msg_before=f"Unable to parse Jira REST API response as JSON: text={response.text}",
                )
                log.modular_input_end(logger, normalized_input_name)
                sys.exit(1)

            jira_issues = response_data["issues"]

            if len(jira_issues) == 0:
                logger.debug(
                    "All API pages have been queried for input {}".format(normalized_input_name)
                )
                new_issues_fetched = False

            # workaround for bug JRASERVER-34746 (worklog field is limited to 20 results)
            if "worklog" in [field.strip() for field in opt_issue_fields.split(",")]:
                for issue in jira_issues:
                    if (
                        ("worklog" in issue["fields"])
                        and ("maxResults" in issue["fields"]["worklog"])
                        and ("total" in issue["fields"]["worklog"])
                    ):
                        # check if the API did not return all worklogs for the issue
                        worklog_max_results = issue["fields"]["worklog"]["maxResults"]
                        worklog_total = issue["fields"]["worklog"]["total"]

                        if worklog_total > worklog_max_results:
                            logger.debug(
                                "The issue {} contains more than {} worklogs. Fetching all worklogs ...".format(
                                    issue["key"], worklog_max_results
                                )
                            )

                            # fetch all worklogs from issue (this endpoint does not support pagination: JRASERVER-69308)
                            try:
                                worklog_response = session.get(
                                    url="https://{}/rest/api/2/issue/{}/worklog".format(
                                        opt_jira_server, issue["key"]
                                    ),
                                    headers=request_headers,
                                )
                            except RequestException as exc:
                                log.log_exception(
                                    logger,
                                    exc,
                                    "Worklog Request Error",
                                    msg_before=f"Unable to send request to Jira REST API to fetch worklogs for input {normalized_input_name} - not all worklogs will be indexed.",
                                )
                                continue

                            if not worklog_response.ok:
                                logger.warning(
                                    "The Jira REST API returned an error when fetching worklogs for issue {} in input {} - not all worklogs will be shown in the event: {}".format(
                                        issue["key"], normalized_input_name, response.text
                                    )
                                )
                                continue

                            # replace worklog in issue object
                            try:
                                issue["fields"]["worklog"] = worklog_response.json()
                            except RequestException as exc:
                                log.log_exception(
                                    logger,
                                    exc,
                                    "Jira API Error",
                                    msg_before=f"Unable to parse Jira issue worklogs as JSON: text={worklog_response.text}",
                                )
                                continue

            # API pagination
            start_at = start_at + response_data["maxResults"]

            # index collected Jira issues
            for issue in jira_issues:
                # extract updated timestamp
                try:
                    updated = datetime.strptime(
                        issue["fields"]["updated"], "%Y-%m-%dT%H:%M:%S.%f%z"
                    )
                except ValueError as exc:
                    log.log_exception(
                        logger,
                        exc,
                        "Time Parsing Error",
                        msg_before=f"Unable to parse updated time of Jira issue - this ticket won't be indexed! Please contact the TA developer! Updated field: {issue['fields']['updated']}",
                    )
                    continue

                try:
                    event = smi.Event(
                        data=json.dumps(issue),
                        time=updated.timestamp(),
                        index=input_item["index"],
                        source=normalized_input_name,
                        sourcetype="jira:issue",
                        done=True,
                        unbroken=True,
                    )
                    event_writer.write_event(event)
                except Exception as exc:
                    log.log_exception(
                        logger, exc, "Indexing Error", msg_before="Unable to write Splunk event"
                    )
                    continue

                # modify last_updated_time if it is later than current value
                if updated > last_updated_time:
                    last_updated_time = updated

                # increase the indexed Jira issue counter
                num_issues_indexed = num_issues_indexed + 1

        # update checkpoint value
        try:
            checkpoint_value = int(last_updated_time.timestamp() * 1000)
            logger.info(
                'Setting new checkpoint value "{}" ({}) for input {} ...'.format(
                    checkpoint_value,
                    last_updated_time.strftime("%Y-%m-%d %H:%M.%f%z"),
                    normalized_input_name,
                )
            )

            kv_checkpoint.update(normalized_input_name, checkpoint_value)
            logger.info("Successfully updated checkpoint!")
        except Exception as exc:
            log.log_exception(
                logger,
                exc,
                "Checkpoint Update Error",
                msg_before="Unable to update checkpoint value - the next input will run with the same checkpoint value, which could lead to duplicate data!",
            )

        if num_issues_indexed > 0:
            logger.info(
                "Successfully indexed {} Jira issues for input {}".format(
                    num_issues_indexed, normalized_input_name
                )
            )
        else:
            logger.info(
                "The input {} ran successfully! There were no (new) Jira issues indexed during this interval.".format(
                    normalized_input_name
                )
            )

        log.events_ingested(
            logger,
            input_name,
            "jira:issue",
            num_issues_indexed,
            input_item["index"],
            opt_service_account,
        )

        log.modular_input_end(logger, normalized_input_name)
