import unittest

from calc.stats import median


class MedianEvenTest(unittest.TestCase):
    def test_even(self):
        self.assertEqual(median([4, 1, 3, 2]), 2.5)
        self.assertEqual(median([1, 2]), 1.5)
        self.assertEqual(median([10, 0, 0, 10]), 5)


if __name__ == "__main__":
    unittest.main()
