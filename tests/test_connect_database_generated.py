import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PROJECT = PROJECT_ROOT / "sample_project"

sys.path.insert(0, str(SAMPLE_PROJECT))

from database import connect_database


def test_connect_database_prints_message(capsys):
    connect_database()

    captured = capsys.readouterr()

    assert captured.out == "Database connection established.\n"


def test_connect_database_returns_none():
    assert connect_database() is None
