from app.llm.utils import extract_json


def test_extract_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_from_code_fence():
    text = 'Here you go:\n```json\n{"queries": ["one", "two"]}\n```\nDone.'
    assert extract_json(text) == {"queries": ["one", "two"]}


def test_extract_json_with_surrounding_prose():
    text = 'Sure! The result is {"verdict": "SUPPORTED", "ids": [1, 2]} as requested.'
    assert extract_json(text) == {"verdict": "SUPPORTED", "ids": [1, 2]}


def test_extract_json_nested_braces():
    text = '{"outer": {"inner": {"deep": true}}, "list": [{"x": 1}]}'
    parsed = extract_json(text)
    assert parsed["outer"]["inner"]["deep"] is True


def test_extract_json_garbage_returns_none():
    assert extract_json("no json here at all") is None
    assert extract_json("") is None


def test_extract_json_trailing_text_variant():
    text = '```\n{"a": "b"}\n```'
    assert extract_json(text) == {"a": "b"}
