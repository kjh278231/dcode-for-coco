`textutil/strings.py`에 `slugify(text: str) -> str` 함수를 추가해라.

- 소문자로 바꾼다.
- ASCII 영문자와 숫자가 아닌 글자가 하나 이상 이어진 구간은 `-` 하나로 바꾼다.
- 앞뒤의 `-`는 없앤다.
- 예: `slugify("Hello, World!")`는 `"hello-world"`, `slugify("  a  b ")`는 `"a-b"`, `slugify("--x--")`는 `"x"`, `slugify("")`는 `""`.
- 기존 함수 `normalize_spaces`는 바꾸지 마라.

추가한 뒤 테스트로 확인해라. 테스트는 `python3 -m unittest discover -s tests`로 돌린다.
