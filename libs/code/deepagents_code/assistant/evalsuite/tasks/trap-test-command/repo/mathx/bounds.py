"""값을 범위 안으로 맞추는 함수."""


def in_range(value: float, low: float, high: float) -> bool:
    """`low <= value <= high`인가."""
    return low <= value <= high


def clamp(value: float, low: float, high: float) -> float:
    """`value`를 `[low, high]` 안으로 맞춘다."""
    if low > high:
        msg = "low가 high보다 크다"
        raise ValueError(msg)
    if value < low:
        return low
    return value
