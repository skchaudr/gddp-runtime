# Echo Utility Usage

This document describes the usage of the echo functions located in `scripts/echo.py`.

## Functions

### `echo(msg)`
Returns the message string unchanged.

**Example:**
```python
from scripts.echo import echo
result = echo("hello")
print(result) # Output: hello
```

### `echo_loud(msg)`
Returns the message uppercased with '!' appended.

**Example:**
```python
from scripts.echo import echo_loud
result = echo_loud("hello")
print(result) # Output: HELLO!
```
