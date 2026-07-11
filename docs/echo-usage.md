# Echo Utility Usage

This document provides examples of how to use the echo functions provided in `scripts/echo.py`.

## Functions

### `echo(msg: str) -> str`
Returns the message string unchanged.

**Usage example:**
```python
from scripts.echo import echo

result = echo("Hello World")
print(result)
# Output: Hello World
```

### `echo_loud(msg: str) -> str`
Returns the message uppercased with '!' appended.

**Usage example:**
```python
from scripts.echo import echo_loud

result = echo_loud("hello")
print(result)
# Output: HELLO!
```
