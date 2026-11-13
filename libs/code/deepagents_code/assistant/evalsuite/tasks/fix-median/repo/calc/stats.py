"""평균과 중앙값."""


def mean(values: list[float]) -> float:
    """산술 평균."""
    if not values:
        msg = "빈 목록"
        raise ValueError(msg)
    return sum(values) / len(values)


def median(values: list[float]) -> float:
    """중앙값."""
    if not values:
        msg = "빈 목록"
        raise ValueError(msg)
    ordered = sorted(values)
    return ordered[len(ordered) // 2]
