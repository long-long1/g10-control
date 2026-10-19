"""Frozen bridge entry; keep the verified protocol/audio implementation intact."""
import sys
import traceback
import argparse
from pathlib import Path

from portable_paths import runtime_paths
from startup_diagnostics import diagnose, prepare_windowed_streams


if __name__ == '__main__':
    if '--diagnose-startup' in sys.argv:
        prepare_windowed_streams()
        sys.exit(diagnose('bridge'))
    try:
        parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
        parser.add_argument('--output', type=Path)
        options, _ = parser.parse_known_args()
        # Reopen the supervisor's log when the windowed bootloader discards
        # Python stdio despite inherited OS handles. Preserve the CLI contract.
        prepare_windowed_streams(options.output.parent / 'service.log' if options.output else None)
        from g10_audio_bridge import main
        main()
    except Exception:
        # Supervised startup errors go to the same writable root as its logs;
        # no modal dialog can strand a headless child process.
        runtime_paths().data_path('logs/g10-bridge-last-error.txt').write_text(
            traceback.format_exc(), encoding='utf-8')
        traceback.print_exc()
        sys.exit(1)
