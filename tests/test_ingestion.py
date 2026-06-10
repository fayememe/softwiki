from softwiki.ingestion.normalize import clean_whitespace, normalize_text
from softwiki.ingestion.dedup import calculate_hash

def test_clean_whitespace():
    assert clean_whitespace(" Hello   World ") == "Hello World"
    assert clean_whitespace("Hello\n\n\nWorld") == "Hello\n\nWorld"

def test_normalize_text():
    assert normalize_text("“Hello” — ‘World’") == '"Hello" - \'World\''
    assert normalize_text("  Spaced   text  ") == "Spaced text"

def test_calculate_hash():
    h1 = calculate_hash("Hello World")
    h2 = calculate_hash("Hello World")
    h3 = calculate_hash("Different Text")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64
