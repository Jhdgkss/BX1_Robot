import json
import unittest

from Robot.mcu_micropython.protocol import PROTOCOL_VERSION, decode_command, frame


class McuProtocolTests(unittest.TestCase):
    def test_versioned_line_frame(self):
        value = json.loads(frame("heartbeat", 4, safe_mode=True))
        self.assertEqual(value["protocol"], PROTOCOL_VERSION)
        self.assertEqual(value["seq"], 4)
        self.assertTrue(value["safe_mode"])

    def test_malformed_and_non_object_frames_rejected(self):
        self.assertIsNone(decode_command("not json"))
        self.assertIsNone(decode_command("[]"))
        self.assertEqual(decode_command('{"command":"scan_i2c"}')['command'], "scan_i2c")


if __name__ == "__main__":
    unittest.main()
