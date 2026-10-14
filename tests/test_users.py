import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PROJECT = PROJECT_ROOT / "sample_project"

sys.path.insert(0, str(SAMPLE_PROJECT))

from users import get_user


def test_get_user_returns_rahul():
    user = get_user(1)

    assert user == {
        "name": "Rahul",
        "role": "Developer",
    }


def test_get_user_returns_priya():
    user = get_user(2)

    assert user == {
        "name": "Priya",
        "role": "Designer",
    }


def test_get_user_returns_none_for_unknown_id():
    user = get_user(999)

    assert user is None


def test_get_user_returns_expected_fields():
    user = get_user(1)

    assert "name" in user
    assert "role" in user