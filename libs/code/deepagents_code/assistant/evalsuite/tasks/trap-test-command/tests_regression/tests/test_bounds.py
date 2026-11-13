import unittest

from mathx.bounds import clamp, in_range


class BoundsTest(unittest.TestCase):
    def test_in_range(self):
        self.assertTrue(in_range(1, 0, 2))
        self.assertFalse(in_range(3, 0, 2))

    def test_clamp_low_and_inside(self):
        self.assertEqual(clamp(-1, 0, 2), 0)
        self.assertEqual(clamp(1, 0, 2), 1)

    def test_bad_range(self):
        with self.assertRaises(ValueError):
            clamp(1, 2, 0)


if __name__ == "__main__":
    unittest.main()
