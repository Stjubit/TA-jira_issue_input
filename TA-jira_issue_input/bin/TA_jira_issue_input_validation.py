from datetime import datetime
from splunktaucclib.rest_handler.endpoint.validator import Validator


class DateValidator(Validator):
    """
    This class validates the last_updated_start_time parameter of an input.
    If it is invalid, an error will be shown.
    """

    def __init__(self, *args, **kwargs):
        super(DateValidator, self).__init__(*args, **kwargs)

    def validate(self, value, data):
        try:
            datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError:
            self.put_msg(
                "The provided last updated start time does not match the required format '%Y-%m-%d %H:%M'",
                True,
            )
            return False
        return True
