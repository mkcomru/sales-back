"""Manual Testing Framework.

Provides reusable components for creating manual API test scripts.

Usage:
    from framework import BaseTestClient, console, setup_environment
    from framework.scenarios import Scenario, run_scenarios
    from framework.output import print_table, success, error
"""

from framework.client import BaseTestClient
from framework.config import Config
from framework.mock_transport import MockTransport
from framework.output import console, error, info, print_json, print_table, success, warn
from framework.scenarios import Scenario, ScenarioResult, interactive_menu, run_scenarios
from framework.setup import setup_environment

__all__ = [
    "BaseTestClient",
    "Config",
    "MockTransport",
    "Scenario",
    "ScenarioResult",
    "interactive_menu",
    "console",
    "error",
    "info",
    "print_json",
    "print_table",
    "run_scenarios",
    "setup_environment",
    "success",
    "warn",
]
