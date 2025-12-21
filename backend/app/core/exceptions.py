from fastapi import HTTPException, status


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

