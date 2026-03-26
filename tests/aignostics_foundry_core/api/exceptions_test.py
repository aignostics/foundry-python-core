"""Tests for aignostics_foundry_core.api.exceptions."""

import pytest
from fastapi.responses import JSONResponse

from aignostics_foundry_core.api.exceptions import (
    AccessDeniedException,
    ApiException,
    NotFoundException,
    api_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)

DEFAULT_STATUS_CODE = 500
NOT_FOUND_STATUS_CODE = 404
ACCESS_DENIED_STATUS_CODE = 401
VALIDATION_STATUS_CODE = 422
SUCCESS_KEY = "success"
ERROR_KEY = "error"


class TestApiException:
    """Tests for ApiException base class."""

    @pytest.mark.unit
    def test_api_exception_defaults(self) -> None:
        """ApiException has status_code 500 and a non-empty default message."""
        exc = ApiException()
        assert exc.status_code == DEFAULT_STATUS_CODE
        assert exc.message

    @pytest.mark.unit
    def test_api_exception_message_override(self) -> None:
        """Custom message parameter is reflected in .message and str()."""
        custom_error = "custom error"
        exc = ApiException(message=custom_error)
        assert exc.message == custom_error
        assert str(exc) == custom_error

    @pytest.mark.unit
    def test_api_exception_status_code_override(self) -> None:
        """Custom status_code parameter is reflected in .status_code."""
        exc = ApiException(status_code=418)
        assert exc.status_code == 418

    @pytest.mark.unit
    def test_not_found_exception_status_code(self) -> None:
        """NotFoundException has status_code 404."""
        exc = NotFoundException()
        assert exc.status_code == NOT_FOUND_STATUS_CODE

    @pytest.mark.unit
    def test_access_denied_exception_status_code(self) -> None:
        """AccessDeniedException has status_code 401."""
        exc = AccessDeniedException()
        assert exc.status_code == ACCESS_DENIED_STATUS_CODE

    @pytest.mark.unit
    def test_not_found_is_api_exception(self) -> None:
        """NotFoundException is a subclass of ApiException."""
        assert isinstance(NotFoundException(), ApiException)

    @pytest.mark.unit
    def test_access_denied_is_api_exception(self) -> None:
        """AccessDeniedException is a subclass of ApiException."""
        assert isinstance(AccessDeniedException(), ApiException)


class TestApiExceptionHandler:
    """Tests for the api_exception_handler function."""

    @pytest.mark.unit
    def test_api_exception_handler_returns_structured_json(self) -> None:
        """Handler returns JSONResponse with success: False and correct code."""
        exc = ApiException(message="something went wrong", status_code=500)
        response: JSONResponse = api_exception_handler(None, exc)  # type: ignore[arg-type]

        assert isinstance(response, JSONResponse)
        assert response.status_code == DEFAULT_STATUS_CODE

        import json

        body = json.loads(bytes(response.body))
        assert body[SUCCESS_KEY] is False
        assert body[ERROR_KEY]["code"] == DEFAULT_STATUS_CODE
        assert body[ERROR_KEY]["message"] == "something went wrong"

    @pytest.mark.unit
    def test_api_exception_handler_propagates_status_code(self) -> None:
        """Handler uses the exception's status_code, not a hard-coded value."""
        exc = NotFoundException()
        response: JSONResponse = api_exception_handler(None, exc)  # type: ignore[arg-type]
        assert response.status_code == NOT_FOUND_STATUS_CODE


class TestUnhandledExceptionHandler:
    """Tests for the unhandled_exception_handler function."""

    @pytest.mark.unit
    def test_unhandled_exception_handler_returns_500(self) -> None:
        """Unhandled exception handler always returns status code 500."""
        response: JSONResponse = unhandled_exception_handler(None, RuntimeError("boom"))  # type: ignore[arg-type]

        assert isinstance(response, JSONResponse)
        assert response.status_code == DEFAULT_STATUS_CODE

        import json

        body = json.loads(bytes(response.body))
        assert body[SUCCESS_KEY] is False
        assert body[ERROR_KEY]["code"] == DEFAULT_STATUS_CODE


class TestValidationExceptionHandler:
    """Tests for the validation_exception_handler function."""

    @pytest.mark.unit
    def test_validation_exception_handler_returns_422(self) -> None:
        """Validation exception handler returns status code 422."""
        # Use FastAPI's RequestValidationError to exercise the errors() path
        from fastapi.exceptions import RequestValidationError
        from pydantic_core import InitErrorDetails, PydanticCustomError

        error = PydanticCustomError("value_error", "bad value")
        exc = RequestValidationError(errors=[InitErrorDetails(type=error, loc=("field",), input="bad")])
        response: JSONResponse = validation_exception_handler(None, exc)  # type: ignore[arg-type]

        assert isinstance(response, JSONResponse)
        assert response.status_code == VALIDATION_STATUS_CODE

        import json

        body = json.loads(bytes(response.body))
        assert body[SUCCESS_KEY] is False
        assert body[ERROR_KEY]["code"] == VALIDATION_STATUS_CODE

    @pytest.mark.unit
    def test_validation_exception_handler_plain_exception_returns_422(self) -> None:
        """Validation handler falls back to str(exc) when errors() is absent."""
        response: JSONResponse = validation_exception_handler(None, ValueError("no errors method"))  # type: ignore[arg-type]
        assert response.status_code == VALIDATION_STATUS_CODE

        import json

        body = json.loads(bytes(response.body))
        assert body[SUCCESS_KEY] is False
