"""Greeting module for Foundry Python Core."""


def greet(name: str) -> str:
    """Return a greeting message for the given name.

    Args:
        name: The name to greet.

    Returns:
        A greeting message in the format "Hello, {name}!".

    Examples:
        >>> greet("World")
        'Hello, World!'
    """
    return f"Hello, {name}!"
