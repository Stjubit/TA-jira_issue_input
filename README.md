# TA-jira_issue_input

TBD

## How to dev

- put your Splunk developer license in the root of this repository in the `splunk.lic` file
- create a file `splunkbase.credentials` in the root of this repository and add Splunkbase credentials (BugMeNot):

```
SPLUNKBASE_USERNAME=<username>
SPLUNKBASE_PASSWORD=<password>
```

- start the Docker instace: `docker compose up [-d]`
