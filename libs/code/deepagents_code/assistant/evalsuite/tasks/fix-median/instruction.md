`calc/stats.py`의 `median`이 원소 개수가 짝수인 목록에서 틀린 값을 돌려준다.

- 짝수 개일 때는 정렬한 뒤 가운데 두 값의 평균을 돌려줘야 한다. 예: `median([4, 1, 3, 2])`는 `2.5`.
- 홀수 개일 때의 동작과 `mean`은 바꾸지 마라.
- 빈 목록이면 지금처럼 `ValueError`를 낸다.

고친 뒤 테스트로 확인해라. 테스트는 `python3 -m unittest discover -s tests`로 돌린다.
