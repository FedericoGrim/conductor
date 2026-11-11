import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from conductor.billing import (
    Balance,
    BillingError,
    RunCost,
    balances,
    ledger_path,
    project_runs,
    read_ledger,
    record_run,
    spend_by_project,
)
from conductor.config import Profile


def profile(name: str, base_url: str, api_key_env: str = "TEST_BILLING_KEY") -> Profile:
    return Profile(name, "provider", base_url, api_key_env, ("provider/m",), "provider/r")


OPENROUTER = profile("medium", "https://openrouter.ai/api/v1")
OPENROUTER_EU = profile("high", "https://eu.openrouter.ai/api/v1")
VERCEL = profile("medium", "https://ai-gateway.vercel.sh/v1")
SCALEWAY = profile("high", "https://api.scaleway.ai/v1")


class FakeApi:
    def __init__(self, responses: dict[str, dict[str, Any] | BillingError]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        self.calls.append((url, headers))
        response = self.responses[url]
        if isinstance(response, BillingError):
            raise response
        return response


@pytest.fixture(autouse=True)
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_BILLING_KEY", "sk-secret")


def test_openrouter_balance_is_purchased_credits_minus_usage() -> None:
    api = FakeApi(
        {
            "https://openrouter.ai/api/v1/credits": {
                "data": {"total_credits": 100.5, "total_usage": 25.75}
            }
        }
    )
    assert balances([OPENROUTER], api) == [
        Balance("openrouter.ai", remaining=74.75, used=25.75, currency="USD")
    ]
    assert api.calls[0][1]["Authorization"] == "Bearer sk-secret"


def test_openrouter_falls_back_to_the_key_limit_without_a_management_key() -> None:
    api = FakeApi(
        {
            "https://openrouter.ai/api/v1/credits": BillingError(403),
            "https://openrouter.ai/api/v1/key": {
                "data": {"limit": 100, "limit_remaining": 74.5, "usage": 25.5}
            },
        }
    )
    assert balances([OPENROUTER], api) == [
        Balance("openrouter.ai", remaining=74.5, used=25.5, note="limit of this API key")
    ]


def test_openrouter_key_without_a_limit_reports_usage_only() -> None:
    api = FakeApi(
        {
            "https://openrouter.ai/api/v1/credits": BillingError(403),
            "https://openrouter.ai/api/v1/key": {
                "data": {"limit": None, "limit_remaining": None, "usage": 3.0}
            },
        }
    )
    assert balances([OPENROUTER], api) == [
        Balance(
            "openrouter.ai",
            remaining=None,
            used=3.0,
            note="account credits need a management key; usage of this API key",
        )
    ]


def test_profiles_sharing_an_account_are_reported_once() -> None:
    api = FakeApi(
        {"https://openrouter.ai/api/v1/credits": {"data": {"total_credits": 10, "total_usage": 4}}}
    )
    assert len(balances([OPENROUTER, OPENROUTER_EU, OPENROUTER], api)) == 1
    assert len(api.calls) == 1


def test_vercel_balance_comes_from_the_credits_endpoint() -> None:
    api = FakeApi(
        {"https://ai-gateway.vercel.sh/v1/credits": {"balance": "95.50", "total_used": "4.50"}}
    )
    assert balances([VERCEL], api) == [Balance("ai-gateway.vercel.sh", remaining=95.5, used=4.5)]


def test_scaleway_reports_the_consumption_of_the_current_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCW_ORGANIZATION_ID", "org-1")
    url = (
        "https://api.scaleway.com/billing/v2beta1/consumptions?organization_id=org-1&page_size=100"
    )
    api = FakeApi(
        {
            url: {
                "consumptions": [
                    {"value": {"currency_code": "EUR", "units": 3, "nanos": 500000000}},
                    {"value": {"currency_code": "EUR", "units": 0, "nanos": 250000000}},
                ]
            }
        }
    )
    assert balances([SCALEWAY], api) == [
        Balance(
            "api.scaleway.ai",
            remaining=None,
            used=3.75,
            currency="EUR",
            note="pay as you go; consumption of the current month",
        )
    ]
    assert api.calls[0][1] == {"X-Auth-Token": "sk-secret"}


def test_scaleway_needs_the_organization_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCW_ORGANIZATION_ID", raising=False)
    assert balances([SCALEWAY], FakeApi({})) == [
        Balance("api.scaleway.ai", note="environment variable SCW_ORGANIZATION_ID is not set")
    ]


def test_missing_key_unknown_provider_and_http_errors_become_notes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_MISSING_KEY", raising=False)
    api = FakeApi({"https://ai-gateway.vercel.sh/v1/credits": BillingError(401)})
    report = balances(
        [
            profile("low", "https://openrouter.ai/api/v1", api_key_env="TEST_MISSING_KEY"),
            profile("medium", "https://llm.example.com/v1"),
            VERCEL,
        ],
        api,
    )
    assert report == [
        Balance("openrouter.ai", note="environment variable TEST_MISSING_KEY is not set"),
        Balance("llm.example.com", note="no balance API known for this provider"),
        Balance("ai-gateway.vercel.sh", note="HTTP 401"),
    ]
    assert "sk-secret" not in repr(report)


def test_a_key_is_never_sent_to_a_base_url_without_tls() -> None:
    api = FakeApi({})
    assert balances([profile("low", "http://openrouter.ai/api/v1")], api) == [
        Balance("openrouter.ai", note="base_url is not https")
    ]
    assert api.calls == []


def test_scaleway_amounts_may_arrive_as_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCW_ORGANIZATION_ID", "org-1")

    def consumptions(url: str, headers: dict[str, str]) -> dict[str, Any]:
        value = {"currency_code": "EUR", "units": "2", "nanos": 500000000}
        return {"consumptions": [{"value": value}]}

    assert balances([SCALEWAY], consumptions)[0].used == 2.5


def test_an_unexpected_response_becomes_a_note() -> None:
    api = FakeApi({"https://ai-gateway.vercel.sh/v1/credits": {"error": "maintenance"}})
    assert balances([VERCEL], api) == [Balance("ai-gateway.vercel.sh", note="unexpected response")]


def test_an_unreachable_provider_becomes_a_note() -> None:
    def unreachable(url: str, headers: dict[str, str]) -> dict[str, Any]:
        raise OSError("name resolution failed")

    assert balances([VERCEL], unreachable) == [
        Balance("ai-gateway.vercel.sh", note="provider unreachable")
    ]


def finished_run(cost: float, finished_at: str = "2026-11-11T10:00:00+00:00") -> dict[str, Any]:
    return {"finished_at": finished_at, "cost": cost, "cost_by_model": {"openrouter/m": cost}}


def test_ledger_lives_under_the_user_data_directory(isolated_data_home: Path) -> None:
    assert ledger_path() == isolated_data_home / "conductor" / "ledger.jsonl"


def test_record_run_appends_one_line_per_run(tmp_path: Path) -> None:
    record_run(tmp_path / "alpha", "openrouter", "run-1", finished_run(0.5))
    record_run(tmp_path / "beta", "scaleway", "run-2", finished_run(0.25))

    assert len(ledger_path().read_text().splitlines()) == 2
    assert read_ledger() == [
        {
            "project": str(tmp_path / "alpha"),
            "run": "run-1",
            "finished_at": "2026-11-11T10:00:00+00:00",
            "provider": "openrouter",
            "cost": 0.5,
            "cost_by_model": {"openrouter/m": 0.5},
        },
        {
            "project": str(tmp_path / "beta"),
            "run": "run-2",
            "finished_at": "2026-11-11T10:00:00+00:00",
            "provider": "scaleway",
            "cost": 0.25,
            "cost_by_model": {"openrouter/m": 0.25},
        },
    ]


def test_read_ledger_is_empty_without_a_file_and_skips_broken_lines() -> None:
    assert read_ledger() == []
    ledger_path().parent.mkdir(parents=True)
    ledger_path().write_text('{"project": "/p", "cost": 1}\nnot json\n[1, 2]\n')
    assert read_ledger() == [{"project": "/p", "cost": 1}]


def test_spend_by_project_sums_runs_finished_since_the_given_moment() -> None:
    entries = [
        {"project": "/alpha", "finished_at": "2026-11-10T09:00:00+00:00", "cost": 0.5},
        {"project": "/alpha", "finished_at": "2026-11-11T09:00:00+00:00", "cost": 0.25},
        {"project": "/beta", "finished_at": "2026-11-01T09:00:00+00:00", "cost": 2.0},
        {"project": "/beta", "finished_at": "2026-09-30T09:00:00+00:00", "cost": 9.0},
        {"project": "/gamma", "finished_at": "garbage", "cost": 9.0},
        {"project": "/gamma", "cost": 9.0},
    ]
    since = datetime(2026, 10, 12, tzinfo=UTC)
    assert spend_by_project(entries, since) == {"/alpha": 0.75, "/beta": 2.0}


def write_run(repo: Path, name: str, run: dict[str, Any]) -> None:
    directory = repo / ".conductor" / "runs" / name
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(json.dumps(run))


def test_project_runs_lists_every_run_oldest_first(tmp_path: Path) -> None:
    write_run(tmp_path, "2026-11-11T10-00-00", finished_run(0.4))
    write_run(tmp_path, "2026-11-10T08-00-00", {"finished_at": "2026-11-10T08:05:00+00:00"})
    (tmp_path / ".conductor" / "runs" / "2026-11-12T00-00-00").mkdir()

    assert project_runs(tmp_path) == [
        RunCost("2026-11-10T08-00-00", "2026-11-10T08:05:00+00:00", None),
        RunCost("2026-11-11T10-00-00", "2026-11-11T10:00:00+00:00", 0.4),
    ]


def test_project_runs_is_empty_for_a_project_never_run(tmp_path: Path) -> None:
    assert project_runs(tmp_path) == []
