import unittest

from textutil.strings import normalize_spaces


class NormalizeSpacesTest(unittest.TestCase):
    def test_collapse(self):
        self.assertEqual(normalize_spaces("  a   b \n c "), "a b c")

    def test_empty(self):
        self.assertEqual(normalize_spaces(""), "")


if __name__ == "__main__":
    unittest.main()
