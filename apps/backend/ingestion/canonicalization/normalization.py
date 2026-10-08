def normalize_match_text(value: str) -> str:
    return " ".join(value.split()).casefold()
