import unittest

from smart_context import decide_action


class SmartContextTests(unittest.TestCase):
    def test_selection_wins_over_editable(self):
        self.assertEqual(decide_action(True, True), "copy")

    def test_selection_copies(self):
        self.assertEqual(decide_action(True, False), "copy")

    def test_editable_without_selection_pastes(self):
        self.assertEqual(decide_action(False, True), "paste")

    def test_unknown_context_is_safe_noop(self):
        self.assertIsNone(decide_action(False, False))


if __name__ == "__main__":
    unittest.main()
