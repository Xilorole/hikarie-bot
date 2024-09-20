from typing import Self


class InvalidPointError(Exception):
    """Raised when the point value is invalid."""

    def __init__(self: Self, point: int, message: str = "Invalid point value") -> None:
        """Initialize the InvalidPointError class."""
        self.point = point
        self.message = message
        super().__init__(f"{message}: {point}")
