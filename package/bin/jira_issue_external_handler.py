from splunktaucclib.rest_handler.admin_external import AdminExternalHandler
from datetime import datetime, timezone, timedelta

import ta_helper


class JiraIssueExternalHandler(AdminExternalHandler):
    """
    Custom REST Handler for Jira issue inputs that supports
    checkpoint deletion when an input is deleted
    """

    def __init__(self, *args, **kwargs):
        AdminExternalHandler.__init__(self, *args, **kwargs)

    def verify_or_update_last_updated_start_time(self):
        # check if last_updated_start_time field is empty
        # if it is empty, set its default value to one week ago
        if not self.payload.get("last_updated_start_time"):
            default_last_updated_start_time = datetime.now(timezone.utc) - timedelta(7)
            self.payload["last_updated_start_time"] = default_last_updated_start_time.strftime(
                "%Y-%m-%d %H:%M"
            )

    def handleList(self, confInfo):  # noqa: N802,N803
        AdminExternalHandler.handleList(self, confInfo)

    def handleCreate(self, confInfo):  # noqa: N802,N803
        self.verify_or_update_last_updated_start_time()

        AdminExternalHandler.handleCreate(self, confInfo)

    def handleEdit(self, confInfo):  # noqa: N802,N803
        AdminExternalHandler.handleEdit(self, confInfo)

    def handleRemove(self, confInfo):  # noqa: N802,N803
        # initialize logger
        logger = ta_helper.initalize_logger(
            "jira-issue",
            self.callerArgs.id,
            "ta_jira_issue_input_settings",
            self.getSessionKey(),
        )

        logger.info(f"Removing check point for input {self.callerArgs.id} ...")

        # initialize KVStore checkpointer
        kv_checkpoint = ta_helper.initialize_checkpointer(
            logger, self.handler._splunkd_uri, self.getSessionKey()
        )

        # delete the checkpoint
        kv_checkpoint.delete(self.callerArgs.id)
        logger.info(f"Successfully removed check point for input {self.callerArgs.id}!")

        AdminExternalHandler.handleRemove(self, confInfo)
