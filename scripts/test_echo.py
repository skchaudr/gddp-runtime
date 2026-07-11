from scripts.echo import echo, echo_loud

def test_echo():
    assert echo("test") == "test"
    assert echo("") == ""
    assert echo("Hello World") == "Hello World"

def test_echo_loud():
    assert echo_loud("test") == "TEST!"
    assert echo_loud("Hello World") == "HELLO WORLD!"
    assert echo_loud("") == "!"
