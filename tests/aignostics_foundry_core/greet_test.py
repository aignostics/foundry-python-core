"""Tests for the greet module."""

import pytest

from aignostics_foundry_core import greet


class TestGreet:
    """Test cases for the greet function."""

    @pytest.mark.unit
    def test_greet_returns_hello_message(self) -> None:
        """Test that greet returns the expected greeting format."""
        result = greet("World")
        assert result == "Hello, World!"

    @pytest.mark.unit
    def test_greet_with_different_names(self) -> None:
        """Test greet with various names."""
        assert greet("Python") == "Hello, Python!"
        assert greet("Alice") == "Hello, Alice!"

    @pytest.mark.unit
    def test_greet_with_empty_string(self) -> None:
        """Test greet with an empty string."""
        assert greet("") == "Hello, !"

    @pytest.mark.unit
    def test_greet_with_special_characters(self) -> None:
        """Test greet handles special characters."""
        assert greet("Test-User_123") == "Hello, Test-User_123!"
