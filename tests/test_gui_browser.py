from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def _free_port() -> int:
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


@pytest.mark.skipif(os.environ.get("HARAKO_GUI_BROWSER") != "1",
                    reason="run explicitly with HARAKO_GUI_BROWSER=1")
def test_real_browser_keyboard_reflow_and_accessible_names() -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    if not EDGE.is_file():
        pytest.skip("local Edge executable is unavailable")
    port = _free_port()
    command = [sys.executable, "-m", "streamlit", "run",
               str(ROOT / "src/harako_gpu/ui/app.py"), "--server.address", "127.0.0.1",
               "--server.port", str(port), "--server.headless", "true",
               "--browser.gatherUsageStats", "false", "--client.showSidebarNavigation", "false"]
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=flags)
    started = time.perf_counter()
    try:
        health = f"http://127.0.0.1:{port}/_stcore/health"
        while True:
            try:
                with urllib.request.urlopen(health, timeout=0.25) as response:
                    if response.status == 200:
                        break
            except OSError:
                pass
            if time.perf_counter() - started > 10:
                pytest.fail("Streamlit health endpoint did not become ready")
            time.sleep(0.05)
        assert time.perf_counter() - started < 2.0
        with playwright.sync_playwright() as runtime:
            browser = runtime.chromium.launch(executable_path=str(EDGE), headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page.goto(f"http://127.0.0.1:{port}", wait_until="networkidle")
            page.get_by_text("Purpose of this page").wait_for()
            assert page.locator("h1").count() == 1
            assert page.get_by_role("combobox", name="Language").count() == 1
            assert page.get_by_role("radiogroup", name="Navigation").count() == 1
            assert page.get_by_text("analysis", exact=True).count() == 0

            focused: set[str] = set()
            focus_visible = False
            for _ in range(16):
                page.keyboard.press("Tab")
                focused.add(page.evaluate("document.activeElement.outerHTML.slice(0, 120)"))
                focus_visible = focus_visible or page.evaluate("""
                    (() => { const s = getComputedStyle(document.activeElement);
                    return (s.outlineStyle !== 'none' && s.outlineWidth !== '0px') ||
                           (s.boxShadow && s.boxShadow !== 'none'); })()
                """)
            assert len(focused) >= 6
            assert page.evaluate("document.activeElement !== document.body")
            assert focus_visible

            # Native desktop widths plus reflow-equivalent widths for
            # 125%, 150%, and 200% zoom on the 900-pixel critical viewport.
            for width in (1920, 1366, 1280, 900, 720, 600, 450):
                page.set_viewport_size({"width": width, "height": 720})
                page.wait_for_timeout(100)
                overflow = page.evaluate(
                    "Math.max(document.body.scrollWidth, document.documentElement.scrollWidth) - "
                    "document.documentElement.clientWidth")
                assert overflow <= 2, f"document overflow at {width}px"
                assert page.get_by_text("Purpose of this page").is_visible()
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=5)
