"""Static safety gates: this MVP must remain offline/local-simulator-only."""

from __future__ import annotations

import ast
from pathlib import Path

from conftest import PRODUCTION_SRC_ROOT, PROJECT_ROOT

BANNED_IMPORT_ROOTS = {
    "aiohttp",
    "alpaca",
    "alpaca_trade_api",
    "http",
    "httpx",
    "ib_insync",
    "importlib",
    "koreainvestment",
    "pykiwoom",
    "requests",
    "socket",
    "ssl",
    "urllib",
    "urllib3",
    "websocket",
    "websockets",
}

BANNED_DYNAMIC_IMPORT_ROOTS = BANNED_IMPORT_ROOTS - {"importlib"}

BANNED_TEXT_TOKENS = {
    ".env",
    "alpaca.markets",
    "api_key",
    "api-secret",
    "apiportal.koreainvestment",
    "appkey",
    "broker_api_key",
    "broker_secret_key",
    "interactivebrokers",
    "openapi.krx",
    "paper-api",
    "secretkey",
}

BANNED_ENV_NAMES = {
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "BROKER_API_KEY",
    "BROKER_SECRET_KEY",
    "KIS_APPKEY",
    "KIS_SECRETKEY",
    "KIWOOM_ACCOUNT",
}

BANNED_REMOTE_ORDER_NAMES = {
    "buy_live",
    "place_order",
    "sell_live",
    "send_order",
    "submit_order",
}


def _production_files() -> list[Path]:
    assert (PROJECT_ROOT / "src").resolve() == PRODUCTION_SRC_ROOT
    assert PRODUCTION_SRC_ROOT.exists(), f"production src root is missing: {PRODUCTION_SRC_ROOT}"
    files = sorted(PRODUCTION_SRC_ROOT.rglob("*.py"))
    assert files, f"no production Python files found under {PRODUCTION_SRC_ROOT}"
    return files


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _import_root(name: str) -> str:
    return name.split(".", 1)[0]


def _constant_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _scan_banned_imports(files: list[Path]) -> list[str]:
    violations: list[str] = []
    for path in files:
        tree = _parse(path)
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [_import_root(alias.name) for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [_import_root(node.module)]
            elif isinstance(node, ast.Call):
                imported = _dynamic_import_roots(node)
            for root in imported:
                if root in BANNED_IMPORT_ROOTS or root in BANNED_DYNAMIC_IMPORT_ROOTS:
                    violations.append(f"{path}: banned import {root}")
    return violations


def _dynamic_import_roots(node: ast.Call) -> list[str]:
    first_arg = _constant_string(node.args[0] if node.args else None)
    if not first_arg:
        return []
    if isinstance(node.func, ast.Name) and node.func.id == "__import__":
        return [_import_root(first_arg)]
    if (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "import_module"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "importlib"
    ):
        return [_import_root(first_arg)]
    return []


def _scan_banned_literals(files: list[Path]) -> list[str]:
    violations: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        for token in BANNED_TEXT_TOKENS:
            if token in text:
                violations.append(f"{path}: banned literal {token}")
    return violations


def _scan_credential_env_reads(files: list[Path]) -> list[str]:
    violations: list[str] = []
    for path in files:
        tree = _parse(path)
        env_aliases = _os_environ_aliases(tree)
        os_aliases = _os_module_aliases(tree)
        getenv_aliases = _os_getenv_aliases(tree)
        for node in ast.walk(tree):
            env_name = _env_lookup_name(node, env_aliases, os_aliases, getenv_aliases)
            if env_name is None:
                continue
            upper = env_name.upper()
            if upper in BANNED_ENV_NAMES or any(
                marker in upper for marker in ("BROKER", "ALPACA", "KIS", "KIWOOM", "SECRET")
            ):
                violations.append(f"{path}: reads trading credential env {env_name}")
    return violations


def _os_module_aliases(tree: ast.AST) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    aliases.add(alias.asname or alias.name)
    return aliases


def _os_environ_aliases(tree: ast.AST) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                if alias.name == "environ":
                    aliases.add(alias.asname or alias.name)
    return aliases


def _os_getenv_aliases(tree: ast.AST) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                if alias.name == "getenv":
                    aliases.add(alias.asname or alias.name)
    return aliases


def _env_lookup_name(
    node: ast.AST,
    env_aliases: set[str],
    os_aliases: set[str],
    getenv_aliases: set[str],
) -> str | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if (
            isinstance(node.func.value, ast.Attribute)
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id in os_aliases
            and node.func.value.attr == "environ"
            and node.func.attr == "get"
        ) or (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id in os_aliases
            and node.func.attr == "getenv"
        ):
            return _constant_string(node.args[0] if node.args else None)
        if (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id in env_aliases
            and node.func.attr == "get"
        ):
            return _constant_string(node.args[0] if node.args else None)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in getenv_aliases
    ):
        return _constant_string(node.args[0] if node.args else None)
    if isinstance(node, ast.Subscript) and (
        (
            isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id in os_aliases
            and node.value.attr == "environ"
        )
        or (isinstance(node.value, ast.Name) and node.value.id in env_aliases)
    ):
        return _constant_string(node.slice)
    return None


def _scan_remote_order_names(files: list[Path]) -> list[str]:
    violations: list[str] = []
    allowed_local_files = {"backtest.py"}
    for path in files:
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name.lower()
                if name in BANNED_REMOTE_ORDER_NAMES and path.name not in allowed_local_files:
                    violations.append(f"{path}: remote-order-like name {node.name}")
    return violations


def test_production_code_does_not_import_network_or_broker_sdks() -> None:
    assert _scan_banned_imports(_production_files()) == []


def test_production_code_has_no_broker_endpoint_or_credential_literals() -> None:
    assert _scan_banned_literals(_production_files()) == []


def test_production_code_does_not_read_trading_credentials_from_environment() -> None:
    assert _scan_credential_env_reads(_production_files()) == []


def test_no_remote_order_submission_function_names_outside_local_simulator() -> None:
    assert _scan_remote_order_names(_production_files()) == []


def test_safety_scan_root_cannot_be_redirected_by_environment() -> None:
    assert (PROJECT_ROOT / "src").resolve() == PRODUCTION_SRC_ROOT


def test_safety_scanner_catches_adversarial_network_and_credential_patterns(
    tmp_path: Path,
) -> None:
    unsafe = tmp_path / "unsafe.py"
    unsafe.write_text(
        "import os as o\n"
        "import socket\n"
        "from os import environ, getenv\n"
        "from os import getenv as ge\n"
        "import importlib\n"
        "API_KEY = environ['BROKER_API_KEY']\n"
        "SECOND = o.getenv('ALPACA_SECRET_KEY')\n"
        "THIRD = getenv('KIS_APPKEY')\n"
        "FOURTH = ge('KIWOOM_ACCOUNT')\n"
        "client = importlib.import_module('requests')\n"
        "def place_order():\n"
        "    return client\n",
        encoding="utf-8",
    )
    files = [unsafe]

    assert _scan_banned_imports(files)
    assert _scan_banned_literals(files)
    assert _scan_credential_env_reads(files)
    assert _scan_remote_order_names(files)
