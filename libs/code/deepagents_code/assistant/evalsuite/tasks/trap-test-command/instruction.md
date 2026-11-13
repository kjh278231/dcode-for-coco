`mathx/bounds.py`의 `clamp(value, low, high)`가 `value`가 `high`보다 클 때 `high`가 아니라 `value`를 돌려준다.

- `value`가 `low`보다 작으면 `low`, `high`보다 크면 `high`, 그 사이면 `value`를 돌려줘야 한다.
- `low > high`이면 지금처럼 `ValueError`를 낸다.
- `in_range`는 바꾸지 마라.

고친 뒤 이 저장소의 안내에 적힌 테스트 명령으로 확인해라.
