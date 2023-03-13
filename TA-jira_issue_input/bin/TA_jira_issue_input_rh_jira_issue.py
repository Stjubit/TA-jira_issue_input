import ta_jira_issue_input_declare  # noqa: F401

from datetime import datetime, timedelta
from solnlib.modular_input import checkpointer
from TA_jira_issue_input_validation import (  # isort: skip
    DateValidator,
)
from splunktaucclib.rest_handler.endpoint import (
    field,
    validator,
    RestModel,
    DataInputModel,
)
from splunktaucclib.rest_handler import admin_external, util
from splunktaucclib.rest_handler.admin_external import AdminExternalHandler

util.remove_http_proxy_env_vars()


fields = [
    field.RestField(
        "interval",
        required=True,
        encrypted=False,
        default=None,
        validator=validator.Pattern(
            regex=r"""^\-[1-9]\d*$|^\d*$""",
        ),
    ),
    field.RestField(
        "index",
        required=True,
        encrypted=False,
        default="default",
        validator=validator.String(
            min_len=1,
            max_len=80,
        ),
    ),
    field.RestField(
        "jql",
        required=True,
        encrypted=False,
        default="updated > -10m",
        validator=validator.String(
            min_len=0,
            max_len=8192,
        ),
    ),
    field.RestField(
        "last_updated_start_time",
        required=False,
        encrypted=False,
        default=None,
        validator=DateValidator(),
    ),
    field.RestField(
        "issue_fields",
        required=True,
        encrypted=False,
        default="summary,description,project,creator,assignee,reporter",
        validator=validator.String(
            min_len=0,
            max_len=8192,
        ),
    ),
    field.RestField(
        "expand_fields",
        required=False,
        encrypted=False,
        validator=validator.String(
            min_len=0,
            max_len=8192,
        ),
    ),
    field.RestField("disabled", required=False, validator=None),
    field.RestField(
        "service_account", required=True, encrypted=False, default=None, validator=None
    ),
]
model = RestModel(fields, name=None)


endpoint = DataInputModel(
    "jira_issue",
    model,
)


class JiraIssueInputRestHandler(AdminExternalHandler):
    """
    Custom REST Handler for Jira issue inputs that supports
    checkpoint deletion when an input is deleted
    """

    def __init__(self, *args, **kwargs):
        AdminExternalHandler.__init__(self, *args, **kwargs)

    def verifyOrUpdateLastUpdatedStartTime(self):
        # check if last_updated_start_time field is empty
        # if it is empty, set its default value to one week ago
        if not self.payload.get("last_updated_start_time"):
            default_last_updated_start_time = datetime.utcnow() - timedelta(7)
            self.payload["last_updated_start_time"] = default_last_updated_start_time.strftime(
                "%Y-%m-%d %H:%M"
            )

    def handleList(self, confInfo):
        AdminExternalHandler.handleList(self, confInfo)

    def handleCreate(self, confInfo):
        self.verifyOrUpdateLastUpdatedStartTime()

        AdminExternalHandler.handleCreate(self, confInfo)

    def handleEdit(self, confInfo):
        AdminExternalHandler.handleEdit(self, confInfo)

    def handleRemove(self, confInfo):
        # delete the checkpoint
        checkpoint = checkpointer.KVStoreCheckpointer(
            "TA_jira_issue_input_checkpointer", self.getSessionKey(), "TA-jira_issue_input"
        )
        checkpoint.delete(self.callerArgs.id)

        AdminExternalHandler.handleRemove(self, confInfo)


if __name__ == "__main__":
    admin_external.handle(
        endpoint,
        handler=JiraIssueInputRestHandler,
    )
