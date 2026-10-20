"""Offline first-frame timing and slow-filesystem isolation; no device/stream is opened."""
import json
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np

from atvv_protocol import AUDIO, CONTROL
from g10_audio_bridge import AudioBuffer, LiveDecoder, LiveRecorder


class StartupLatencyTests(unittest.TestCase):
    def recorder(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        events, stop = queue.Queue(maxsize=64), threading.Event()
        rec = LiveRecorder(Path(temp.name) / 'case', events, stop)
        self.addCleanup(rec.close)
        return rec, events, stop

    def test_prebuffer_and_callback_timing_are_measured_without_changing_threshold(self):
        sink = AudioBuffer()
        decoder = LiveDecoder(sink, Mock(), False)
        start = 1_000_000_000
        decoder.event(CONTROL, bytes.fromhex('04030201'), start)
        out = np.empty((480, 2), dtype=np.float32)
        for offset in (0, 16):
            with patch('g10_audio_bridge.time.perf_counter_ns', return_value=start + (offset + 1) * 1_000_000):
                decoder.event(AUDIO, bytes([0x12]) * 128, start + offset * 1_000_000)
                sink.read_into(out)
            self.assertEqual(sink.rendered, 0)
            self.assertIsNone(sink.startup_snapshot()['first_output_callback_ns'])
        with patch('g10_audio_bridge.time.perf_counter_ns', return_value=start + 33_000_000):
            decoder.event(AUDIO, bytes([0x12]) * 128, start + 32_000_000)
        with patch('g10_audio_bridge.time.perf_counter_ns', return_value=start + 40_000_000):
            sink.read_into(out)
        timing = sink.startup_snapshot()
        self.assertEqual(sink.threshold, 2304)  # Unchanged 48 ms at 48 kHz.
        self.assertEqual(decoder.samples, 768)
        self.assertEqual(sink.rendered, 480)
        self.assertEqual(timing['first_audio_to_pcm_ms'], 1)
        self.assertEqual(timing['first_pcm_to_output_callback_ms'], 39)
        self.assertEqual(timing['start_to_output_callback_ms'], 40)
        self.assertTrue(np.any(out))
        sink.read_into(out)
        self.assertEqual(sink.startup_snapshot(), timing)
        decoder.event(CONTROL, bytes.fromhex('0002'), start + 100_000_000)
        decoder.event(CONTROL, bytes.fromhex('04030202'), start + 200_000_000)
        self.assertIsNone(sink.startup_snapshot()['first_pcm_ns'])

    def test_audio_before_start_keeps_original_callback_timestamp(self):
        sink = AudioBuffer()
        decoder = LiveDecoder(sink, Mock(), False)
        decoder.event(AUDIO, bytes(128), 999_000_000)
        decoder.event(CONTROL, bytes.fromhex('04030201'), 1_000_000_000)
        self.assertEqual(sink.startup_snapshot()['start_to_first_audio_ms'], -1)
        self.assertEqual(sink.frames, 768)

    def test_blocked_log_write_cannot_hold_first_pcm_or_output_callback(self):
        rec, events, stop = self.recorder()
        stream = rec.stream
        entered, release = threading.Event(), threading.Event()

        def blocked_write(value):
            entered.set()
            if not release.wait(3):
                raise TimeoutError('test writer was not released')
            return stream.write(value)

        rec.stream = Mock(write=blocked_write, close=stream.close)
        self.addCleanup(release.set)
        perf = time.perf_counter_ns()
        rec.notification(CONTROL, bytes.fromhex('04030201'), perf, time.time_ns(), 'offline')
        self.assertTrue(entered.wait(1))
        sink = AudioBuffer()
        decoder = LiveDecoder(sink, rec, False)
        decoder.event(*events.get_nowait())
        for _ in range(3):
            rec.notification(AUDIO, bytes([0x12]) * 128, time.perf_counter_ns(), time.time_ns(), 'offline')
            decoder.event(*events.get_nowait())
        out = np.empty((480, 2), dtype=np.float32)
        sink.read_into(out)
        self.assertEqual(sink.rendered, 480)
        self.assertFalse(release.is_set())
        self.assertFalse(stop.is_set())
        release.set()
        rec.flush()
        self.assertEqual(rec.audio_bytes, 384)
        self.assertEqual(rec.counts['audio'], 3)
        rec.close()
        rows = [json.loads(row) for row in (rec.directory / 'events.jsonl').read_text().splitlines()]
        self.assertEqual(rows[0]['perf_ns'], perf)
        self.assertEqual(rows[0]['kind'], 'control')
        self.assertEqual(sum(row['kind'] == 'audio' for row in rows), 3)
        self.assertFalse((rec.directory / 'audio-notifications.bin').exists())

    def test_failed_writer_sets_stop_and_cannot_claim_success(self):
        rec, _, stop = self.recorder()
        stream = rec.stream
        rec.stream = Mock(write=Mock(side_effect=OSError('offline disk error')), close=stream.close)
        rec.emit('test')
        rec.flush()
        self.assertTrue(stop.is_set())
        self.assertIn('offline disk error', rec.errors[0])
        rec.emit('ble_cleanup_complete', errors=list(rec.errors))  # Cleanup may still emit without raising.
        self.assertTrue(rec.write_error)

    def test_log_queue_is_bounded_and_overflow_stops_instead_of_blocking(self):
        rec, _, stop = self.recorder()
        stream = rec.stream
        entered, release = threading.Event(), threading.Event()

        def blocked_write(value):
            entered.set()
            if not release.wait(3):raise TimeoutError('test writer was not released')
            return stream.write(value)

        rec.stream = Mock(write=blocked_write, close=stream.close)
        self.addCleanup(release.set)
        rec.emit('first')
        self.assertTrue(entered.wait(1))
        for _ in range(rec.log_events.maxsize):rec.emit('queued')
        rec.emit('overflow')
        self.assertTrue(stop.is_set())
        self.assertIn('evidence incomplete', rec.errors[0])
        release.set()
        rec.flush()
        self.assertEqual(rec.counts['queued'], 512)


if __name__ == '__main__':unittest.main()
