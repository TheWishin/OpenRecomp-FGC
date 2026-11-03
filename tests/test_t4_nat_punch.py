"""The vendored T4 lobby client's hole punching: an answer to a punch is never answered without end.

Two game sockets on 127.0.0.1 (nothing leaves this PC). One punch makes at most one answer from each side;
without new punches the traffic stops (review t4-online-b740a3a finding 2).
"""
import asyncio
import os
import unittest
from unittest import mock

from openrecomp.vendor.t4lobby import nat, proto


TAG = b"m" * 8


class PunchAnswers(unittest.TestCase):
    def test_one_punch_is_answered_once_and_the_traffic_stops(self):
        async def run():
            with mock.patch.dict(os.environ, {"T5_NET_BIND": "127.0.0.1"}):
                server = ("127.0.0.1", 9)
                a = await nat.GameSocket.open(0, server, 0, b"t" * 16, TAG, 0)
                b = await nat.GameSocket.open(0, server, 0, b"u" * 16, TAG, 1)
            try:
                to_b, to_a = ("127.0.0.1", b.port), ("127.0.0.1", a.port)
                a._punch_to(to_b)
                await asyncio.sleep(0.3)
                first = (a.stats["tx"], b.stats["tx"])
                await asyncio.sleep(0.4)
                self.assertEqual((a.stats["tx"], b.stats["tx"]), first)      # nothing circling
                self.assertLessEqual(sum(first), 3)
                self.assertIn(to_b, a.confirmed)                            # the handshake still completes
                a._punch_to(to_b)                                           # a new punch is answered again
                await asyncio.sleep(0.3)
                self.assertIn(to_a, b.confirmed)
                self.assertGreater(b.stats["tx"], first[1])
                # An older peer that answers every punch, answers included: still one answer per seq here.
                before = b.stats["tx"]
                for _ in range(5):
                    b.datagram_received(proto.pk_punch(TAG, 0, proto.F_HEARD, 4242), to_a)
                self.assertEqual(b.stats["tx"], before + 1)
            finally:
                await a.close()
                await b.close()
        asyncio.run(run())

    def test_the_answered_list_stays_small(self):
        async def run():
            with mock.patch.dict(os.environ, {"T5_NET_BIND": "127.0.0.1"}):
                a = await nat.GameSocket.open(0, ("127.0.0.1", 9), 0, b"t" * 16, TAG, 0)
            sent = []
            a.send = lambda data, addr, ttl=None: sent.append(addr)        # nothing on the wire
            try:
                for seq in range(2000):
                    a.datagram_received(proto.pk_punch(TAG, 1, 0, seq), ("127.0.0.1", 9999))
                self.assertLessEqual(len(a.answered), 512)
                self.assertEqual(len(sent), 2000)                               # every new punch answered
            finally:
                await a.close()
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
