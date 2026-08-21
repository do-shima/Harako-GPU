set shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

install:
    python -m venv .venv
    .venv\Scripts\python -m pip install -e ".[test]"

test:
    .venv\Scripts\python -m pytest

doctor:
    .venv\Scripts\harako-gpu doctor --json

