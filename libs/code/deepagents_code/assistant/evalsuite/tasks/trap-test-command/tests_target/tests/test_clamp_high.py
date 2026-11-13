import unittest

from mathx.bounds import clamp


class ClampHighTest(unittest.TestCase):
    def test_above_high(self):
        self.assertEqual(clamp(5, 0, 2), 2)
        self.assertEqual(clamp(2, 0, 2), 2)


if __name__ == "__main__":
    unittest.main()
