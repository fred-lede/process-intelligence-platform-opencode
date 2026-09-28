"""Frozen-executable entry point for the analysis engine.

PyInstaller freezes this module into a standalone executable so the Tauri
bundle can ship the engine without requiring a system Python or a
virtualenv on the end-user machine.

The process contract (JSON lines over stdin/stdout) is byte-for-byte the
same as running ``python -m process_intelligence_engine.main``.
"""

from __future__ import annotations

from process_intelligence_engine.main import main

if __name__ == "__main__":
    raise SystemExit(main())
