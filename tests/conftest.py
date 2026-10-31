"""Shared test setup. Every test runs with the app-level network lock installed,
so any accidental outbound connection makes the test suite fail."""

import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from productiontools.core import netguard  # noqa: E402

FIX = ROOT / "fixtures"
TEMPLATE = FIX / "templates" / "bluebird_lane_topsheet.xlsx"
PROFILE = FIX / "templates" / "bluebird_lane_topsheet.profile.yaml"


@pytest.fixture(autouse=True, scope="session")
def _network_lock():
    netguard.install()
    yield


@pytest.fixture
def chart():
    return {str(k): v for k, v in yaml.safe_load((FIX / "account_codes.yaml").read_text()).items()}


@pytest.fixture
def template_copy(tmp_path):
    p = tmp_path / "template.xlsx"
    shutil.copy(TEMPLATE, p)
    return p
