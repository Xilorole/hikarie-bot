from typing import Self


class CheckerFunctionNotSpecifiedError(Exception):
    """Raised when the checker function is not specified."""

    def __init__(self: Self) -> None:
        """Initialize the CheckerFunctionNotSpecifiedError class."""
        super().__init__("The checker function is not specified.")


class AchievementAlreadyRegisteredError(Exception):
    """Raised when the user has already achieved the badge."""

    def __init__(self: Self) -> None:
        """Initialize the AchievementAlreadyRegisteredError class."""
        super().__init__("User has already achieved the badge")


class UserArrivalNotFoundError(Exception):
    """Raised when the user arrival data is not found."""

    def __init__(self: Self, arrival_id: int) -> None:
        """Initialize the UserArrivalNotFoundError class."""
        super().__init__(f"User arrival not found for arrival_id: {arrival_id}")
