import unittest

from textutil.strings import slugify


class SlugifyTest(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")
        self.assertEqual(slugify("  a  b "), "a-b")
        self.assertEqual(slugify("--x--"), "x")
        self.assertEqual(slugify(""), "")

    def test_digits_and_symbols(self):
        self.assertEqual(slugify("Rev 2.0 (beta)"), "rev-2-0-beta")


if __name__ == "__main__":
    unittest.main()
