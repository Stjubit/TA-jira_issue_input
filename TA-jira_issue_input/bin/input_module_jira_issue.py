# encoding = utf-8
import sys
import base64
import json

from datetime import datetime


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

    # API pagination
    # maxResults is not used, because every Jira server can have different limits
    # total is not used, because it is not included in the response for expensive searches
    start_at = 0
    new_issues_fetched = True
    num_issues_indexed = 0

    while new_issues_fetched:
        # get Jira issues via REST API
        helper.log_info(
            "Sending request to Jira REST API (startAt={}, input={})".format(
                start_at, opt_input_name
            )
        )

        request_params = {
            "jql": opt_jql,
            "fields": "updated,{}".format(opt_issue_fields),
            "validateQuery": "true",
            "startAt": start_at,
        }

        if opt_expand_fields:
            request_params["expand"] = opt_expand_fields

        request_headers = {
            "Authorization": "Basic {}".format(
                base64.b64encode("{}:{}".format(opt_username, opt_password).encode("ascii")).decode(
                    "ascii"
                )
            )
        }
        response = helper.send_http_request(
            url="https://{}/rest/api/2/search".format(opt_jira_server),
            method="GET",
            parameters=request_params,
            verify=opt_verify_cert,
            headers=request_headers,
        )

        if not response.ok:
            helper.log_critical(
                "The Jira REST API returned an error when fetching issues for input {}: {}".format(
                    opt_input_name, response.text
                )
            )
            sys.exit(1)

        # check if new issues have been fetched (otherwise all pages have been queried)
        response_data = response.json()
        jira_issues = response_data["issues"]

        if len(jira_issues) == 0:
            helper.log_debug("All API pages have been queried for input {}".format(opt_input_name))
            new_issues_fetched = False

        # API pagination
        start_at = start_at + response_data["maxResults"]

        # index collected Jira issues
        for issue in jira_issues:
            # extract updated timestamp
            updated = datetime.strptime(issue["fields"]["updated"], "%Y-%m-%dT%H:%M:%S.%f%z")

            event = helper.new_event(
                time=updated.timestamp(),
                source=opt_input_name,
                index=helper.get_output_index(),
                sourcetype=helper.get_sourcetype(),
                data=json.dumps(issue),
            )
            ew.write_event(event)

        num_issues_indexed = num_issues_indexed + len(jira_issues)

    helper.log_info(
        "Successfully indexed {} Jira issues for input {}".format(
            num_issues_indexed, opt_input_name
        )
    )
