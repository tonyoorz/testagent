import unittest

from agent.core.session_manager import SessionManager


class SessionManagerTests(unittest.TestCase):
    def test_get_or_create_returns_same_session_for_same_key(self):
        manager = SessionManager()

        first = manager.get_or_create('chat:defect', dashboard_type='defect')
        second = manager.get_or_create('chat:defect', dashboard_type='defect')

        self.assertIs(first, second)
        self.assertEqual(first.session_id, 'chat:defect')
        self.assertEqual(first.dashboard_type, 'defect')
        self.assertIsNotNone(first.query_memory)
        self.assertIsNotNone(first.data_context)


if __name__ == '__main__':
    unittest.main()