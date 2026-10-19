import asyncio
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest

from atvv_protocol import TX,CONTROL,CAPABILITIES,capabilities
from phase2_handshake import Controller
from phase2_readonly import Recorder

class FakeTX:
    uuid=TX
    characteristic_properties=4
    def __init__(self): self.sent=[]
    async def write_value_with_option_async(self,value,option):
        self.sent.append(bytes(value)); return 0

class HandshakeTests(unittest.TestCase):
    def test_no_open_before_capabilities_and_only_one_open_while_active(self):
        async def exercise(c):
            c.receive(CONTROL,b'\x08',time.perf_counter_ns())
            self.assertTrue(c.queue.empty())
            c.requested=True
            c.receive(CONTROL,bytes.fromhex('0b 01 00 00 02 00 78'),time.perf_counter_ns())
            c.initialized=True
            c.receive(CONTROL,b'\x08',time.perf_counter_ns())
            c.receive(CONTROL,b'\x08',time.perf_counter_ns())
            self.assertEqual(c.queue.qsize(),1)
            await c.tick()
            self.assertEqual(c.tx.sent,[bytes.fromhex('0c 00')])
            c.receive(CONTROL,bytes.fromhex('04 00 02 07'),time.perf_counter_ns())
            await c.close()
            self.assertEqual(c.tx.sent[-1],bytes.fromhex('0d 07'))
        self.run_case(exercise)

    def test_stop_overtakes_queued_open(self):
        async def exercise(c):
            c.caps=capabilities(bytes.fromhex('0b 01 00 02 00 00 78')); c.initialized=True
            c.receive(CONTROL,b'\x08',1)
            c.receive(CONTROL,b'\x00',2)
            await c.tick(); await c.close()
            self.assertEqual(c.tx.sent,[])
        self.run_case(exercise)

    def test_device_initiated_start_after_capabilities_matches_source(self):
        async def exercise(c):
            c.caps=capabilities(bytes.fromhex('0b 01 00 02 03 00 80')); c.initialized=True
            c.receive(CONTROL,bytes.fromhex('04 03 02 01'),1)
            self.assertTrue(c.streaming)
            self.assertFalse(c.stop.is_set())
            self.assertEqual(c.session_id,1)
            self.assertFalse(c.opened)
            await c.close()
            self.assertEqual(c.tx.sent,[bytes.fromhex('0d 01')])
        self.run_case(exercise)

    def test_whitelist_and_rejected_capabilities(self):
        async def exercise(c):
            with self.assertRaises(RuntimeError): await c.send('GET_CAPABILITIES',b'\x00')
            self.assertEqual(c.tx.sent,[])
            c.requested=True
            c.receive(CONTROL,bytes.fromhex('0b 01 00 01 00 00 78'),1)
            self.assertTrue(c.stop.is_set())
            self.assertIsNone(c.caps)
            await c.close()
            self.assertEqual(c.tx.sent,[])
        self.run_case(exercise)

    def test_initialize_single_request_receives_capability_and_close_after_failed_open(self):
        async def exercise(c):
            async def reply():
                await asyncio.sleep(.01)
                c.receive(CONTROL,bytes.fromhex('0b 01 00 00 02 00 78'),1)
            task=asyncio.create_task(reply())
            await c.initialize(); await task
            self.assertEqual(c.tx.sent,[CAPABILITIES])
            c.opened=True
            await c.close()
            self.assertEqual(c.tx.sent[-1],bytes.fromhex('0d 00'))
        self.run_case(exercise)

    def run_case(self,fn):
        with tempfile.TemporaryDirectory() as t:
            rec=Recorder(Path(t)/'case')
            try:
                c=Controller(rec,threading.Event(),queue.Queue()); c.tx=FakeTX()
                asyncio.run(fn(c))
            finally:
                rec.close()

if __name__=='__main__': unittest.main()
