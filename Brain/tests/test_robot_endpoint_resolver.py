import unittest
from unittest.mock import patch

from bx1_modules.robot_endpoint_resolver import RobotEndpointResolver


class ResolverTests(unittest.TestCase):
    def test_local_preferred(self):
        self.assertEqual(RobotEndpointResolver().preferred, 'http://192.168.68.54:8088')

    @patch('bx1_modules.robot_endpoint_resolver.request.urlopen')
    def test_fallback_and_recovery(self, opener):
        opener.side_effect = [OSError('local down'), type('R', (), {'status': 200, '__enter__': lambda s:s, '__exit__': lambda *a:None})(), type('R', (), {'status': 200, '__enter__': lambda s:s, '__exit__': lambda *a:None})()]
        r = RobotEndpointResolver()
        self.assertIn('100.72.130.12', r.choose())
        r._last_probe = 0
        self.assertIn('192.168.68.54', r.choose())


if __name__ == '__main__':
    unittest.main()
