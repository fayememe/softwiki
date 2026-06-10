import re

def clean_whitespace(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = clean_whitespace(text)
    smart_quotes = {
        '“': '"', '”': '"', '‘': "'", '’': "'",
        '—': '-', '–': '-'
    }
    for char, replacement in smart_quotes.items():
        text = text.replace(char, replacement)
    return text
