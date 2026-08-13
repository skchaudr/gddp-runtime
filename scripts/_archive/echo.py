def echo(msg: str) -> str:
    """Returns the message string unchanged."""
    return msg

def echo_loud(msg: str) -> str:
    """Returns the message uppercased with '!' appended."""
    return f"{msg.upper()}!"

if __name__ == "__main__":
    # Basic tests
    assert echo("test") == "test"
    assert echo("") == ""
    assert echo_loud("test") == "TEST!"
    assert echo_loud("") == "!"
    print("All tests passed!")
