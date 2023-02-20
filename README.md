# TA-jira_issue_input

This Splunk Technical Add-on enables you to index Jira issues by querying your Jira servers' REST API. You can control which issues to index by specifying a JQL query string.

**Example:**

`project = SD AND updated > -15m`

- this JQL query string matches all issues in the service desk (SD) project that have been updated during the last 15 minutes

## Configuration

1. Setup the Jira Account by going to the configuration page of the TA-jira_issue_input app: **Configuration** -> **Account**

- **Account Name** | Unique name of the account
- **Jira Server** | Jira Server Hostname (without `http(s)://`)
- **Verify Jira Server Certificate** | Whether the Jira server certificate should be verified
- **Username** | Jira REST API username
- **Password** | Jira REST API password

2. *(Optional)* Setup a proxy to use for the requests to the Jira REST API: **Configuration** -> **Proxy**

3. Add your Jira issue input on the app **Inputs** configuration page

- **Name** | Unique name of the data input (this also represents the `source` field)
- **Interval** | Time interval of input in seconds
- **Index** | The destination index in which the Jira issue data will be stored
- **Jira Account** | The Jira account configured in step 1
- **JQL (Jira Query Language)** | The JQL query string defines which issues to collect
- **Issue Fields** | Comma-separated list of Jira issue fields to collect. This config option also supports wildcards like \*all. More infos can be found [here](https://docs.atlassian.com/software/jira/docs/api/REST/latest/#search-search).
- **Expand Fields** | *(optional)* Comma-separated list of entities to expand. More infos can be found [here](https://docs.atlassian.com/software/jira/docs/api/REST/latest/).

## Additional Notes

This TA includes a workaround for [JRASERVER-34746](https://jira.atlassian.com/browse/JRASERVER-34746), which means you can use the `worklog` field to fetch all worklogs.

## How to dev

- Put your Splunk developer license in the root of this repository in a file called `splunk.lic`
- Create a file with the name `splunkbase.credentials` in the root of this repository and add working Splunkbase credentials in it *(hint: BugMeNot)*:

```
SPLUNKBASE_USERNAME=<username>
SPLUNKBASE_PASSWORD=<password>
```

- Start the Docker instace: `docker compose up [-d]`
