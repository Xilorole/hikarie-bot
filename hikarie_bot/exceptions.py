from typing import Self


class CheckerFunctionNotSpecifiedError(Exception):
    """Raised when the checker function is not specified."""

    def __init__(self: Self) -> None:
        """Initialize the CheckerFunctionNotSpecifiedError class."""
        super().__init__("The checker function is not specified.")
