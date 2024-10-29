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


class EnvironmentVariableNotFoundError(Exception):
    """Raised when the environment variable is not found."""

    def __init__(self: Self, env_var: str) -> None:
        """Initialize the EnvironmentVariableNotFoundError class."""
        super().__init__(f"Environment variable not found: {env_var}")


class InvalidPointError(Exception):
    """Raised when the point value is invalid."""

    def __init__(self: Self, point: int, message: str = "Invalid point value") -> None:
        """Initialize the InvalidPointError class."""
        self.point = point
        self.message = message
        super().__init__(f"{message}: {point}")
