"""문자열 정리 함수."""


def normalize_spaces(text: str) -> str:
    """연속한 공백을 하나로 줄이고 앞뒤 공백을 없앤다."""
    return " ".join(text.split())
