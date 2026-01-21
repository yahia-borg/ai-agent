"""
Custom exceptions for the application.
"""
from typing import Dict, Any, Optional
from fastapi import HTTPException, status


class ToolError(Exception):
    """
    Structured exception for tool errors.
    Allows supervisor to make intelligent recovery decisions.
    """
    def __init__(
        self,
        message: str,
        error_code: str,
        recoverable: bool = True,
        context: Optional[Dict[str, Any]] = None,
        retry_after: Optional[int] = None
    ):
        """
        Initialize ToolError.
        
        Args:
            message: Human-readable error message
            error_code: Machine-readable error code (e.g., "QUOTATION_NOT_FOUND", "INVALID_INPUT")
            recoverable: Whether the error can be recovered from (default: True)
            context: Additional context about the error (default: None)
            retry_after: Seconds to wait before retry (default: None)
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.recoverable = recoverable
        self.context = context or {}
        self.retry_after = retry_after
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for JSON serialization."""
        return {
            "error": self.message,
            "error_code": self.error_code,
            "recoverable": self.recoverable,
            "context": self.context,
            "retry_after": self.retry_after
        }
    
    def __str__(self) -> str:
        return f"{self.error_code}: {self.message}"


# Common error codes
class ErrorCodes:
    """Standard error codes for tool errors."""
    # Quotation errors
    QUOTATION_NOT_FOUND = "QUOTATION_NOT_FOUND"
    QUOTATION_ALREADY_EXISTS = "QUOTATION_ALREADY_EXISTS"
    INVALID_QUOTATION_ID = "INVALID_QUOTATION_ID"
    
    # Data errors
    MISSING_REQUIRED_DATA = "MISSING_REQUIRED_DATA"
    INVALID_DATA_FORMAT = "INVALID_DATA_FORMAT"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    
    # Database errors
    DB_CONNECTION_ERROR = "DB_CONNECTION_ERROR"
    DB_QUERY_ERROR = "DB_QUERY_ERROR"
    DB_TRANSACTION_ERROR = "DB_TRANSACTION_ERROR"
    
    # External service errors
    LLM_ERROR = "LLM_ERROR"
    SEARCH_SERVICE_ERROR = "SEARCH_SERVICE_ERROR"
    EXPORT_SERVICE_ERROR = "EXPORT_SERVICE_ERROR"
    
    # Validation errors
    INVALID_INPUT = "INVALID_INPUT"
    INPUT_TOO_LONG = "INPUT_TOO_LONG"
    MISSING_PARAMETER = "MISSING_PARAMETER"
    
    # System errors
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


# HTTP Exceptions (for API endpoints)
class QuotationNotFoundError(HTTPException):
    def __init__(self, quotation_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quotation {quotation_id} not found"
        )


class QuotationNotCompletedError(HTTPException):
    def __init__(self, quotation_id: str, current_status: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Quotation {quotation_id} is not completed (current status: {current_status})"
        )


class LLMServiceError(HTTPException):
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM service error: {message}"
        )
