import unittest

from agent.core.session_data_context import SessionDataContext


class SessionDataContextTests(unittest.TestCase):
    def test_update_from_request_tracks_request_fields(self):
        context = SessionDataContext(dashboard_type='defect')

        context.update_from_request(
            {
                'question': 'show weekly defects',
                'page_context': {'selected_team': 'DTSV_China'},
                'page_filters': {'project': ['MGU']},
                'data_summary': 'summary',
            }
        )

        snapshot = context.to_dict()
        self.assertEqual(snapshot['dashboard_type'], 'defect')
        self.assertEqual(snapshot['last_question'], 'show weekly defects')
        self.assertEqual(snapshot['page_context']['selected_team'], 'DTSV_China')
        self.assertEqual(snapshot['page_filters'], {'project': ['MGU']})
        self.assertEqual(snapshot['data_summary'], 'summary')


if __name__ == '__main__':
    unittest.main()