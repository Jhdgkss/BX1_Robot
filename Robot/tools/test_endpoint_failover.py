import unittest
from unittest.mock import Mock, patch

from bx1_robot_client import BX1BrainClient, BrainClientConfig, EndpointResolver


class FakeResponse:
    status_code = 200
    text = '{}'
    def json(self): return {}


class EndpointFailoverTests(unittest.TestCase):
    def test_local_is_preferred_and_candidates_are_ordered(self):
        r = EndpointResolver('', [])
        self.assertEqual(r.candidates[:2], ['http://192.168.68.53:8765', 'http://100.92.216.101:8765'])

    @patch('bx1_robot_client.requests.get')
    def test_tailscale_fallback_and_return_local(self, get):
        get.side_effect = [OSError('local down'), FakeResponse(), FakeResponse()]
        r = EndpointResolver('', [])
        self.assertIn('100.92.216.101', r.choose())
        r._last_probe = 0
        self.assertIn('192.168.68.53', r.choose())

    @patch('bx1_robot_client.requests.get')
    def test_cached_local_success_does_not_probe_tailscale(self, get):
        get.return_value = FakeResponse()
        r = EndpointResolver('', [])
        self.assertEqual(r.choose(), 'http://192.168.68.53:8765')
        self.assertEqual(get.call_count, 1)
        self.assertEqual(r.choose(), 'http://192.168.68.53:8765')
        self.assertEqual(get.call_count, 1)
        self.assertNotIn('100.92.216.101', [call.args[0] for call in get.call_args_list])

    @patch('bx1_robot_client.requests.get')
    def test_fallback_periodically_reprobes_lan(self, get):
        get.side_effect = [OSError('lan down'), FakeResponse(), FakeResponse()]
        r = EndpointResolver('', [])
        self.assertEqual(r.choose(), 'http://100.92.216.101:8765')
        r._last_probe = 0
        self.assertEqual(r.choose(), 'http://192.168.68.53:8765')
        self.assertEqual(get.call_args_list[2].args[0], 'http://192.168.68.53:8765/api/status')

    @patch('bx1_robot_client.requests.post')
    @patch('bx1_robot_client.requests.get')
    def test_post_has_one_request_id_and_is_not_replayed(self, get, post):
        get.return_value = FakeResponse()
        post.return_value = FakeResponse()
        client = BX1BrainClient(BrainClientConfig(''))
        client.chat('BX1', 'hello')
        self.assertEqual(post.call_count, 1)
        payload = post.call_args.kwargs['json']
        self.assertTrue(payload['request_id'])
        self.assertEqual(post.call_args.kwargs['headers']['X-BX1-Request-ID'], payload['request_id'])


if __name__ == '__main__':
    unittest.main()
