"""Synthetic notification-to-output-callback benchmark. Never opens BLE or audio streams."""
import argparse
import ast
import json
from pathlib import Path
import queue
import statistics
import tempfile
import threading
import time

import numpy as np

from atvv_protocol import AUDIO, CONTROL
from g10_audio_bridge import AudioBuffer, LiveDecoder, LiveRecorder, Upsample3
from analyze_audio import Decoder
from phase2_readonly import Recorder


def old_classes(root):
    # Compile only these classes into an isolated namespace: no module import,
    # main(), hardware setup or writes to the old checkout, including pycache.
    source = ast.parse((root / 'g10_audio_bridge.py').read_text(encoding='utf-8'))
    names = {'AudioBuffer', 'Upsample3', 'LiveDecoder', 'LiveRecorder'}
    nodes = [node for node in source.body if isinstance(node, ast.ClassDef) and node.name in names]
    if {node.name for node in nodes} != names:raise ValueError('Old bridge classes missing')
    from collections import deque
    namespace = dict(np=np, threading=threading, time=time, deque=deque,
                     Decoder=Decoder, Recorder=Recorder, AUDIO=AUDIO, CONTROL=CONTROL)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<read-only-old-bridge-classes>', 'exec'), namespace)
    return tuple(namespace[name] for name in ('AudioBuffer', 'LiveDecoder', 'LiveRecorder'))


def measure(classes, delay_ms, rounds):
    buffer_class, decoder_class, recorder_class = classes
    elapsed = []
    for _ in range(rounds):
        with tempfile.TemporaryDirectory(prefix='g10-startup-offline-') as temp:
            events = queue.Queue(maxsize=64)
            rec = recorder_class(Path(temp) / 'case', events)
            stream = rec.stream

            class DelayedMetadataStream:
                def write(self, value):
                    if delay_ms:time.sleep(delay_ms / 1000)
                    return stream.write(value)
                def close(self):stream.close()

            rec.stream = DelayedMetadataStream()
            sink = buffer_class()
            decoder = decoder_class(sink, rec, False)
            delivered = threading.Event()
            errors = []
            def consume():
                try:
                    for _ in range(4):
                        decoder.event(*events.get(timeout=3))
                    out = np.empty((480, 2), dtype=np.float32)
                    sink.read_into(out)  # Memory copy only, not a PortAudio stream.
                    if sink.rendered != 480 or not np.any(out):
                        raise AssertionError('Expected decoded PCM output')
                    delivered.set()
                except Exception as exc:errors.append(repr(exc))

            worker = threading.Thread(target=consume)
            worker.start()
            started = time.perf_counter_ns()
            try:
                packets = [(CONTROL, bytes.fromhex('04030201'))] + [(AUDIO, bytes([0x12]) * 128)] * 3
                for key, data in packets:
                    rec.notification(key, data, time.perf_counter_ns(), time.time_ns(), 'synthetic')
                if not delivered.wait(3):raise RuntimeError('Offline pipeline failed: '+str(errors))
                elapsed.append((time.perf_counter_ns() - started) / 1e6)
            finally:
                worker.join()
                rec.close()
    ordered = sorted(elapsed)
    return {'rounds': rounds, 'median_ms': round(statistics.median(elapsed), 3),
            'max_ms': round(ordered[-1], 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-root', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 100:parser.error('rounds must be 1..100')
    old = old_classes(args.old_root)
    new = (AudioBuffer, LiveDecoder, LiveRecorder)
    result = {'scope': 'Three audio frames in one synthetic burst; memory output callback; same decoder in both cases. Not physical key/BLE/WASAPI latency.',
              'cases': []}
    for delay in (0, 20):
        result['cases'].append({'injected_metadata_write_delay_ms': delay,
                                'old': measure(old, delay, args.rounds),
                                'new': measure(new, delay, args.rounds)})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':main()
