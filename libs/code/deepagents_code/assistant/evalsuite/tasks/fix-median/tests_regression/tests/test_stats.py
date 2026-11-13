import unittest

from calc.stats import mean, median


class StatsTest(unittest.TestCase):
    def test_mean(self):
        self.assertEqual(mean([1, 2, 3, 4]), 2.5)

    def test_median_odd(self):
        self.assertEqual(median([3, 1, 2]), 2)
        self.assertEqual(median([5]), 5)

    def test_empty(self):
        with self.assertRaises(ValueError):
            median([])
        with self.assertRaises(ValueError):
            mean([])


if __name__ == "__main__":
    unittest.main()
