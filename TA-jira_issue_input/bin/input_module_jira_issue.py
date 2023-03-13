# encoding = utf-8
import sys
import base64
import json
import re

from requests.exceptions import RequestException
from datetime import datetime, timedelta, timezone


def _parse_datetime(helper, datetimestr):
    """
    This function is used to validate and parse a given Jira datetime string
    """
    try:
        return datetime.strptime(datetimestr, "%Y-%m-%d %H:%M")
    except ValueError:
        helper.log_warning(
            "The provided last updated start time does not match the required format '%Y-%m-%d %H:%M'"
        )
        return None


def validate_input(helper, definition):
    # it is not possible to retrieve Global Account information in the `validate_input` function
    # because setup_util is not yet initialized
    jql = definition.parameters.get("jql", None)
    if not jql:
        raise Exception("You have to enter a valid JQL")

    issue_fields = definition.parameters.get("issue_fields", None)
    if not issue_fields:
        raise Exception("You have to enter Jira Issue fields to collect")

    # check if issue field list is valid
    for field in issue_fields.split(","):
        if len(field.strip()) == 0:
            raise Exception("You have entered an invalid comma-separated list of issue fields")


def collect_events(helper, ew):
    """
    This function queries the Jira REST API to collect Jira issue data
    and indexes them in Splunk accordingly
    """
    # set log level
    helper.set_log_level(helper.get_log_level())

    # get input options
    opt_jql = helper.get_arg("jql")
    opt_last_updated_start_time = helper.get_arg("last_updated_start_time")
    opt_issue_fields = helper.get_arg("issue_fields")
    opt_expand_fields = helper.get_arg("expand_fields")  # optional
    opt_service_account = helper.get_arg("service_account")
    opt_input_name = helper.get_input_stanza_names()

    # validate input options
    if not opt_jql or not opt_issue_fields or not opt_service_account:
        helper.log_critical("The input {} is not configured properly".format(opt_input_name))
        sys.exit(1)

    # get account options
    opt_jira_server = (
        opt_service_account["jira_server"] if "jira_server" in opt_service_account else None
    )
    opt_username = opt_service_account["username"] if "username" in opt_service_account else None
    opt_password = opt_service_account["password"] if "password" in opt_service_account else None
    opt_verify_cert = (
        opt_service_account["verify_jira_server_certificate"] == "1"
        if "verify_jira_server_certificate" in opt_service_account
        else None
    )

    # validate global account
    if not opt_jira_server or not opt_username or not opt_password or opt_verify_cert is None:
        helper.log_critical(
            "The global account with ID {} is not configured properly".format(opt_service_account)
        )
        sys.exit(1)

    # check if checkpoint already exists
    checkpoint_value = helper.get_check_point(opt_input_name)

    if checkpoint_value is None:
        helper.log_info(
            "The checkpoint for input {} does not yet exist! Initializing checkpoint ...".format(
                opt_input_name
            )
        )

        default_last_updated_start_time = datetime.utcnow() - timedelta(7)
        checkpoint_value = int(default_last_updated_start_time.timestamp() * 1000)

        if opt_last_updated_start_time:
            helper.log_info(
                "A last updated start time has been configured for the input! Validating timestamp ..."
            )

            last_updated_start_time = _parse_datetime(helper, opt_last_updated_start_time)
            if last_updated_start_time is not None:
                # set checkpoint to last_updated_start_time
                helper.log_info("The provided last updated start time is valid!")
                checkpoint_value = int(last_updated_start_time.timestamp() * 1000)
            else:
                # use the default last updated start time
                helper.log_warning(
                    "The provided last updated start time is invalid - the checkpoint will be initialized with default values!"
                )
        else:
            helper.log_info(
                "The input started without a last updated start time setting - the checkpoint will be initialized with default values!"
            )

        helper.log_info(
            "Initializing checkpoint with value '{}' ({})".format(
                checkpoint_value,
                datetime.fromtimestamp(checkpoint_value / 1000).strftime("%Y-%m-%d %H:%M UTC"),
            )
        )

        try:
            helper.save_check_point(opt_input_name, checkpoint_value)
            helper.log_info("Successfully initialized checkpoint!")
        except Exception as exc:
            helper.log_critical(
                "Unable to initialize checkpoint - the input can't be started! Exception: {}".format(
                    exc
                )
            )
            sys.exit(1)

    # split JQL to check for updated field
    jql_parts = [part.lower() for part in re.split("[^a-zA-Z]", opt_jql)]
    helper.log_debug("JQL splitted parts: {}".format(jql_parts))

    # verify if checkpoint should be used for data collection or not
    if ("updated" in jql_parts) or ("updateddate" in jql_parts):
        helper.log_info(
            "Starting input {} without using the checkpoint, because an updated field has been set in the JQL filter!".format(
                opt_input_name
            )
        )
    else:
        helper.log_info(
            "Starting input {} with checkpoint value {} ({})!".format(
                opt_input_name,
                checkpoint_value,
                datetime.fromtimestamp(checkpoint_value / 1000).strftime("%Y-%m-%d %H:%M.%f UTC"),
            )
        )

        # add checkpoint value to JQL
        opt_jql = "updated > {} AND {}".format(checkpoint_value, str(opt_jql).strip())
        helper.log_debug("Updated JQL: {}".format(opt_jql))

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
        helper.log_info(
            "Sending request to Jira REST API (startAt={}, input={})".format(
                start_at, opt_input_name
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

        helper.log_debug("Request parameters for Jira REST API: {}".format(request_params))

        request_headers = {
            "Authorization": "Basic {}".format(
                base64.b64encode("{}:{}".format(opt_username, opt_password).encode("ascii")).decode(
                    "ascii"
                )
            )
        }

        try:
            response = helper.send_http_request(
                url="https://{}/rest/api/2/search".format(opt_jira_server),
                method="GET",
                parameters=request_params,
                verify=opt_verify_cert,
                headers=request_headers,
            )
        except RequestException as exc:
            helper.log_critical(
                "Unable to send request to Jira REST API for input {}: {}".format(
                    opt_input_name, exc
                )
            )
            sys.exit(1)

        if not response.ok:
            helper.log_critical(
                "The Jira REST API returned an error when fetching issues for input {}: {}".format(
                    opt_input_name, response.text
                )
            )
            sys.exit(1)

        # check if new issues have been fetched (otherwise all pages have been queried)
        try:
            response_data = response.json()
        except RequestException as exc:
            helper.log_critical(
                "Unable to parse Jira REST API response as JSON: text={}, exc={}".format(
                    response.text, exc
                )
            )
            sys.exit(1)

        jira_issues = response_data["issues"]

        if len(jira_issues) == 0:
            helper.log_debug("All API pages have been queried for input {}".format(opt_input_name))
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
                        helper.log_debug(
                            "The issue {} contains more than {} worklogs. Fetching all worklogs ...".format(
                                issue["key"], worklog_max_results
                            )
                        )

                        # fetch all worklogs from issue (this endpoint does not support pagination: JRASERVER-69308)
                        try:
                            worklog_response = helper.send_http_request(
                                url="https://{}/rest/api/2/issue/{}/worklog".format(
                                    opt_jira_server, issue["key"]
                                ),
                                method="GET",
                                verify=opt_verify_cert,
                                headers=request_headers,
                            )
                        except RequestException as exc:
                            helper.log_error(
                                "Unable to send request to Jira REST API to fetch worklogs for input {} - not all worklogs will be indexed: {}".format(
                                    opt_input_name, exc
                                )
                            )
                            continue

                        if not worklog_response.ok:
                            helper.log_warning(
                                "The Jira REST API returned an error when fetching worklogs for issue {} in input {} - not all worklogs will be shown in the event: {}".format(
                                    issue["key"], opt_input_name, response.text
                                )
                            )
                            continue

                        # replace worklog in issue object
                        try:
                            issue["fields"]["worklog"] = worklog_response.json()
                        except RequestException as exc:
                            helper.log_critical(
                                "Unable to parse Jira issue worklogs as JSON: text={}, exc={}".format(
                                    worklog_response.text, exc
                                )
                            )
                            continue

        # API pagination
        start_at = start_at + response_data["maxResults"]

        # index collected Jira issues
        for issue in jira_issues:
            # extract updated timestamp
            try:
                updated = datetime.strptime(issue["fields"]["updated"], "%Y-%m-%dT%H:%M:%S.%f%z")
            except ValueError:
                helper.log_critical(
                    "Unable to parse updated time of Jira issue - this ticket won't be indexed! Please contact the TA developer! Updated field: {}".format(
                        issue["fields"]["updated"]
                    )
                )
                continue

            try:
                event = helper.new_event(
                    time=updated.timestamp(),
                    source=opt_input_name,
                    index=helper.get_output_index(),
                    sourcetype=helper.get_sourcetype(),
                    data=json.dumps(issue),
                )
                ew.write_event(event)
            except Exception as exc:
                helper.log_critical("Unable to write Splunk event: {}".format(exc))
                continue

            # modify last_updated_time if it is later than current value
            if updated > last_updated_time:
                last_updated_time = updated

            # increase the indexed Jira issue counter
            num_issues_indexed = num_issues_indexed + 1

    # update checkpoint value
    try:
        checkpoint_value = int(last_updated_time.timestamp() * 1000)
        helper.log_info(
            'Setting new checkpoint value "{}" ({}) for input {} ...'.format(
                checkpoint_value, last_updated_time.strftime("%Y-%m-%d %H:%M.%f%z"), opt_input_name
            )
        )
        helper.save_check_point(opt_input_name, checkpoint_value)
        helper.log_info("Successfully updated checkpoint!")
    except Exception as exc:
        helper.log_critical(
            "Unable to update checkpoint value - the next input will run with the same checkpoint value, which could lead to duplicate data! Exception: {}".format(
                exc
            )
        )

    if num_issues_indexed > 0:
        helper.log_info(
            "Successfully indexed {} Jira issues for input {}".format(
                num_issues_indexed, opt_input_name
            )
        )
    else:
        helper.log_info(
            "The input {} ran successfully! There were no (new) Jira issues indexed during this interval.".format(
                opt_input_name
            )
        )
