"""Error handling utilities mirroring the TypeScript errorHandler."""

from enum import Enum
from typing import Any


class ErrorType(str, Enum):
    NOT_FOUND = "NOT_FOUND"
    VALIDATION = "VALIDATION"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    DATABASE = "DATABASE"
    INTERNAL = "INTERNAL"


class AppError(Exception):
    """Custom application error with type and status code."""

    def __init__(
        self,
        message: str,
        error_type: ErrorType,
        status_code: int,
        details: Any = None,
    ):
        super().__init__(message)
        self.type = error_type
        self.status_code = status_code
        self.details = details
        self.name = "AppError"


def handle_database_error(error: Exception) -> AppError:
    """Map database errors to AppError instances.

    In the TS version this handled Prisma-specific error codes.
    Here we map common SQLAlchemy / generic DB exceptions.
    """
    from verifier_api.utils.logger import logger

    if isinstance(error, AppError):
        return error

    error_str = str(error)

    # Unique constraint violation
    if "UNIQUE constraint" in error_str or "IntegrityError" in error_str:
        return AppError(
            "A record with this value already exists.",
            ErrorType.VALIDATION,
            409,
        )

    # Not found
    if "NoResultFound" in error_str:
        return AppError("Record not found.", ErrorType.NOT_FOUND, 404)

    logger.error("Unknown database error: %s", error)
    return AppError("An unexpected error occurred.", ErrorType.INTERNAL, 500)
