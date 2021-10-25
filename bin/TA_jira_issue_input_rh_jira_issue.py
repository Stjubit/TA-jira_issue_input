
import ta_jira_issue_input_declare

from splunktaucclib.rest_handler.endpoint import (
    field,
    validator,
    RestModel,
    DataInputModel,
)
from splunktaucclib.rest_handler import admin_external, util
from splunk_aoblib.rest_migration import ConfigMigrationHandler

util.remove_http_proxy_env_vars()


fields = [
    field.RestField(
        'interval',
        required=True,
        encrypted=False,
        default=None,
        validator=validator.Pattern(
            regex=r"""^\-[1-9]\d*$|^\d*$""", 
        )
    ), 
    field.RestField(
        'index',
        required=True,
        encrypted=False,
        default='default',
        validator=validator.String(
            min_len=1, 
            max_len=80, 
        )
    ),
    field.RestField(
        'jql',
        required=True,
        encrypted=False,
        default='updated > -10m',
        validator=validator.String(
            min_len=0, 
            max_len=8192, 
        )
    ), 
    field.RestField(
        'issue_fields',
        required=True,
        encrypted=False,
        default='summary,description,project,creator,assignee,reporter',
        validator=validator.String(
            min_len=0, 
            max_len=8192, 
        )
    ), 
    field.RestField(
        'expand_fields',
        required=False,
        encrypted=False,
        validator=validator.String(
            min_len=0, 
            max_len=8192, 
        )
    ), 
    field.RestField(
        'disabled',
        required=False,
        validator=None
    ),
    field.RestField(
        'service_account',
        required=True,
        encrypted=False,
        default=None,
        validator=None
    ), 
]
model = RestModel(fields, name=None)



endpoint = DataInputModel(
    'jira_issue',
    model,
)


if __name__ == '__main__':
    admin_external.handle(
        endpoint,
        handler=ConfigMigrationHandler,
    )
