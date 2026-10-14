from app.text_utils import slugify


def test_lowercases():
    assert slugify("Hello") == "hello"


def test_spaces_become_hyphens():
    assert slugify("hello world") == "hello-world"


def test_punctuation_removed():
    assert slugify("Hello, World!") == "hello-world"


def test_collapses_repeated_separators():
    assert slugify("a   b---c") == "a-b-c"


def test_strips_leading_and_trailing():
    assert slugify("  --Hello--  ") == "hello"


def test_empty_returns_empty():
    assert slugify("") == ""


def test_digits_kept():
    assert slugify("Python 3.11 rocks") == "python-311-rocks"
