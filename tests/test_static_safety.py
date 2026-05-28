"""Static safety gates: this MVP must remain offline/local-simulator-only."""

from __future__ import annotations

import ast
from pathlib import Path

from conftest import PRODUCTION_SRC_ROOT

BANNED_IMPORT_ROOTS = {
    "alpaca",
    "alpaca_trade_api",
    "httpx",
    "ib_insync",
    "koreainvestment",
    "pykiwoom",
    "requests",
    "urllib",
    "websocket",
    "websockets",
}

BANNED_TEXT_TOKENS = {
    "alpaca.markets",
    "paper-api",
    "apiportal.koreainvestment",
    "openapi.krx",
    "interactivebrokers",
    "secretkey",
    "appkey",
    ".env",
}

BANNED_ENV_NAMES = {
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "KIS_APPKEY",
    "KIS_SECRETKEY",
    "KIWOOM_ACCOUNT",
    "BROKER_API_KEY",
    "BROKER_SECRET_KEY",
}

BANNED_REMOTE_ORDER_NAMES = {
    "submit_order",
    "place_order",
    "send_order",
    "buy_live",
    "sell_live",
}


def _production_files() -> list[Path]:
    assert PRODUCTION_SRC_ROOT.exists(), f"production src root is missing: {PRODUCTION_SRC_ROOT}"
    files = sorted(PRODUCTION_SRC_ROOT.rglob("*.py"))
    assert files, f"no production Python files found under {PRODUCTION_SRC_ROOT}"
    return files


def test_production_code_does_not_import_network_or_broker_sdks() -> None:
    violations: list[str] = []
    for path in _production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module.split(".", 1)[0]]
            else:
                continue
            for root in imported:
                if root in BANNED_IMPORT_ROOTS:
                    violations.append(f"{path}: banned import {root}")
    assert violations == []


def test_production_code_has_no_broker_endpoint_or_credential_literals() -> None:
    violations: list[str] = []
    for path in _production_files():
        text = path.read_text(encoding="utf-8").lower()
        for token in BANNED_TEXT_TOKENS:
            if token in text:
                violations.append(f"{path}: banned literal {token}")
    assert violations == []


def test_production_code_does_not_read_trading_credentials_from_environment() -> None:
    violations: list[str] = []
    for path in _production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                is_env_lookup = (
                    isinstance(node.func.value, ast.Attribute)
                    and isinstance(node.func.value.value, ast.Name)
                    and node.func.value.value.id == "os"
                    and node.func.value.attr == "environ"
                    and node.func.attr in {"get", "__getitem__"}
                ) or (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                    and node.func.attr == "getenv"
                )
                if not is_env_lookup:
                    continue
                first_arg = node.args[0] if node.args else None
                if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                    env_name = first_arg.value.upper()
                    if env_name in BANNED_ENV_NAMES or any(
                        marker in env_name for marker in ("BROKER", "ALPACA", "KIS", "KIWOOM")
                    ):
                        violations.append(f"{path}: reads trading credential env {first_arg.value}")
    assert violations == []


def test_no_remote_order_submission_function_names_outside_local_simulator() -> None:
    violations: list[str] = []
    allowed_local_files = {"backtest.py"}
    for path in _production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name.lower()
                if name in BANNED_REMOTE_ORDER_NAMES and path.name not in allowed_local_files:
                    violations.append(f"{path}: remote-order-like name {node.name}")
    assert violations == []
