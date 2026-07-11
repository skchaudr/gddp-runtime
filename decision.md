# Implementation Decision

## Decision
Implemented a simple Python module in `scripts/echo.py` with two functions: `echo` and `echo_loud`.

## Rationale
- `echo(msg)`: The requirement specifies returning the message string unchanged. It simply returns the input string.
- `echo_loud(msg)`: The requirement specifies returning the message uppercased with '!' appended. This can be easily achieved using string manipulation `f"{msg.upper()}!"` for simplicity and readability.
- The use of type hints (`str`) helps with potential static type checking and provides clearer documentation of expected argument types.
