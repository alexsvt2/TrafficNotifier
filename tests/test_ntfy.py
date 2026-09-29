import unittest

from traffic_notifier.ntfy import parse_event


class ParseEventTest(unittest.TestCase):
    def test_message(self):
        message = parse_event(b'{"id":"abc","time":1790000000,"event":"message","message":"revisar"}\n')
        self.assertEqual((message.id, message.text), ("abc", "revisar"))

    def test_keepalive_and_open_are_ignored(self):
        self.assertIsNone(parse_event(b'{"id":"k","time":1,"event":"keepalive"}'))
        self.assertIsNone(parse_event(b'{"id":"o","time":1,"event":"open"}'))

    def test_invalid_json_is_ignored(self):
        self.assertIsNone(parse_event(b"no es json"))


if __name__ == "__main__":
    unittest.main()
