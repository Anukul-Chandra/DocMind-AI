import re


def clean_text(text: str) -> str:
    """Clean extracted text by normalizing whitespace and blank lines.

    Args:
        text: The text to clean.

    Returns:
        The cleaned text with normalized whitespace.
    """
    text = text.strip()
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text
