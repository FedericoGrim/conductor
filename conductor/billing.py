from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from conductor import credentials
from conductor.config import Profile, Provider

Get = Callable[[str, dict[str, str]], dict[str, Any]]

SCALEWAY_ORGANIZATION_ENV = "SCW_ORGANIZATION_ID"
SCALEWAY_CONSUMPTIONS_URL = "https://api.scaleway.com/billing/v2beta1/consumptions"


class BillingError(RuntimeError):
    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status


@dataclass(frozen=True)
class Balance:
    account: str
    remaining: float | None = None
    used: float | None = None
    currency: str = "USD"
    note: str = ""


BalanceReader = Callable[[str, Provider, str, Get], Balance]


def http_get(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={**headers, "User-Agent": "conductor-billing"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload: dict[str, Any] = json.loads(response.read())
            return payload
    except urllib.error.HTTPError as error:
        raise BillingError(error.code) from error


def openrouter_balance(account: str, provider: Provider, api_key: str, get: Get) -> Balance:
    base_url = provider.base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        credits = get(f"{base_url}/credits", headers)["data"]
    except BillingError as error:
        if error.status != 403:
            raise
    else:
        used = float(credits["total_usage"])
        return Balance(account, remaining=float(credits["total_credits"]) - used, used=used)
    key = get(f"{base_url}/key", headers)["data"]
    if key.get("limit_remaining") is None:
        note = "account credits need a management key; usage of this API key"
        return Balance(account, used=float(key["usage"]), note=note)
    return Balance(
        account,
        remaining=float(key["limit_remaining"]),
        used=float(key["usage"]),
        note="limit of this API key",
    )


def vercel_balance(account: str, provider: Provider, api_key: str, get: Get) -> Balance:
    url = f"{provider.base_url.rstrip('/')}/credits"
    credits = get(url, {"Authorization": f"Bearer {api_key}"})
    return Balance(account, remaining=float(credits["balance"]), used=float(credits["total_used"]))


def scaleway_balance(account: str, provider: Provider, api_key: str, get: Get) -> Balance:
    organization = os.environ.get(SCALEWAY_ORGANIZATION_ENV)
    if not organization:
        return Balance(account, note=f"environment variable {SCALEWAY_ORGANIZATION_ENV} is not set")
    query = urllib.parse.urlencode({"organization_id": organization, "page_size": 100})
    consumptions = get(f"{SCALEWAY_CONSUMPTIONS_URL}?{query}", {"X-Auth-Token": api_key})
    values = [item["value"] for item in consumptions.get("consumptions", [])]
    return Balance(
        account,
        used=sum(
            float(value.get("units", 0)) + float(value.get("nanos", 0)) / 1e9 for value in values
        ),
        currency=values[0]["currency_code"] if values else "EUR",
        note="pay as you go; consumption of the current month",
    )


BALANCE_READERS: dict[str, BalanceReader] = {
    "openrouter.ai": openrouter_balance,
    "ai-gateway.vercel.sh": vercel_balance,
    "api.scaleway.ai": scaleway_balance,
}


def balance_reader(host: str) -> tuple[str, BalanceReader] | None:
    for domain, reader in BALANCE_READERS.items():
        if host == domain or host.endswith("." + domain):
            return domain, reader
    return None


def account_balance(
    provider: Provider, host: str, reader: BalanceReader | None, get: Get
) -> Balance:
    if reader is None:
        return Balance(host, note="no balance API known for this provider")
    api_key = credentials.api_key(provider.api_key_env)
    if not api_key:
        return Balance(host, note=f"no API key: {provider.api_key_env} is not set or stored")
    try:
        return reader(host, provider, api_key, get)
    except BillingError as error:
        return Balance(host, note=str(error))
    except OSError:
        return Balance(host, note="provider unreachable")
    except (KeyError, TypeError, ValueError):
        return Balance(host, note="unexpected response")


def balances(profiles: Iterable[Profile], get: Get | None = None) -> list[Balance]:
    get = get or http_get
    seen: set[tuple[str, str]] = set()
    report: list[Balance] = []
    for profile in profiles:
        for provider in profile.providers.values():
            url = urllib.parse.urlsplit(provider.base_url)
            host = url.hostname or provider.base_url
            known = balance_reader(host)
            account = (known[0] if known else host, provider.api_key_env)
            if account in seen:
                continue
            seen.add(account)
            if url.scheme != "https":
                report.append(Balance(host, note="base_url is not https"))
                continue
            report.append(account_balance(provider, host, known[1] if known else None, get))
    return report


@dataclass(frozen=True)
class RunCost:
    run: str
    finished_at: str | None
    cost: float | None


def ledger_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data_home) / "conductor" / "ledger.jsonl"


def record_run(project: Path, provider: str, run_name: str, run: dict[str, Any]) -> None:
    entry = {
        "project": str(project),
        "run": run_name,
        "finished_at": run.get("finished_at"),
        "provider": provider,
        "cost": run.get("cost", 0.0),
        "cost_by_model": run.get("cost_by_model", {}),
    }
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as ledger:
        ledger.write(json.dumps(entry) + "\n")


def read_json_object(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def read_ledger() -> list[dict[str, Any]]:
    path = ledger_path()
    if not path.exists():
        return []
    entries = (read_json_object(line) for line in path.read_text().splitlines())
    return [entry for entry in entries if entry is not None]


def finished_since(entry: dict[str, Any], since: datetime) -> bool:
    try:
        return datetime.fromisoformat(str(entry.get("finished_at"))) >= since
    except ValueError:
        return False


def spend_by_project(entries: list[dict[str, Any]], since: datetime) -> dict[str, float]:
    totals: dict[str, float] = {}
    for entry in entries:
        cost = entry.get("cost")
        if isinstance(cost, int | float) and finished_since(entry, since):
            project = str(entry.get("project"))
            totals[project] = totals.get(project, 0.0) + cost
    return totals


def project_runs(repo: Path) -> list[RunCost]:
    runs: list[RunCost] = []
    for run_file in sorted((repo / ".conductor" / "runs").glob("*/run.json")):
        run = read_json_object(run_file.read_text()) or {}
        cost = run.get("cost")
        runs.append(
            RunCost(
                run=run_file.parent.name,
                finished_at=run.get("finished_at"),
                cost=float(cost) if isinstance(cost, int | float) else None,
            )
        )
    return runs
