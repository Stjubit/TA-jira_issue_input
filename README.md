# TA-jira_issue_input

This Splunk Technical Add-on enables you to index Jira issues by querying your Jira servers' REST API. You can control which issues to index by specifying a JQL query string.

**Example:**

`project = SD AND status != "Canceled"`

- This JQL query string matches all issues in the service desk (SD) project that haven't been canceled.

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
- **JQL (Jira Query Language)** | The JQL (Jira Query Language) search filter defines which Jira issues to collect (more infos: [Advanced Searching](http://confluence.atlassian.com/display/JIRA/Advanced+Searching)). If you filter for the `updated` field, the input does not use checkpoints to only index the latest data!
- **Last Updated Start Time** | The start time for the input defines which Jira issues should be collected based on their last updated time. Format: `YYYY-MM-DD hh:mm` (UTC). Default: 1 week ago. This field only applies if you DO NOT specify the `updated` field in the JQL search filter!
- **Issue Fields** | Comma-separated list of Jira issue fields to collect. This config option also supports wildcards like \*all. More infos can be found [here](https://docs.atlassian.com/software/jira/docs/api/REST/latest/#search-search).
- **Expand Fields** | *(optional)* Comma-separated list of entities to expand. More infos can be found [here](https://docs.atlassian.com/software/jira/docs/api/REST/latest/).

## Checkpoints

This app uses [KV Store checkpoints](https://splunk.github.io/addonfactory-solutions-library-python/modular_input/checkpointer/#solnlib.modular_input.checkpointer.KVStoreCheckpointer) to save the latest state of an input in order to only index updated Jira issues since the last run. This feature has been added in version `1.1.0` of this TA.

### How to view checkpoint values

You can use the `jira_issue_input_checkpointer_lookup` lookup to view the current checkpoint value(s). **Example search:**

```
| inputlookup jira_issue_input_checkpointer_lookup
| eval input_name=_key
```

### How to reindex Jira issues

You can easily reindex data by modifying the checkpoint value for an input. The timestamp has to be an integer in milliseconds! **Example search:**

```
| inputlookup jira_issue_input_checkpointer_lookup
| search _key="<input_name>"
| eval state="1678718462404"
| outputlookup jira_issue_input_checkpointer_lookup
```

*Please note that checkpoints are only used if you do not specify an `updated` field in your JQL!*

Of course, you can also just delete and create a new input to reindex data!

## Update Notes

### 1.0.x to > 1.1.0

Version `1.1.0` added checkpoint support to the TA by adding a new field to the input called `Last Updated Start Time` (`last_updated_start_time`).

Your inputs will continue to work the same way after upgrading from `1.0.x` to `1.1.x`, but I highly recommend to migrate to checkpoints. There are two ways how you can do this:

1. Update the TA and let your inputs run at least one time. This will initialize the checkpoint with `updated` timestamps from the input. You can disable and enable an input to make it run manually. After that, you can just edit your inputs and remove filters for the `updated` field from your JQL. This will make sure that the input now uses the checkpoint for data retrieval.
2. Reconfigure your inputs and set the `Last Updated Start Time` field to the last time the old input was running. Remove filters for the `updated` field from your JQL.

## Additional Notes

This TA includes a workaround for [JRASERVER-34746](https://jira.atlassian.com/browse/JRASERVER-34746), which means you can use the `worklog` field to fetch all worklogs.

## How to dev

- Put your Splunk developer license in the root of this repository in a file called `splunk.lic`
- Start the Docker instace: `docker compose up [-d]`
