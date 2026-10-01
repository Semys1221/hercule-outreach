"""Tests for grok_usage billing parse and fetch."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from grok_usage import (
    GrokUsageSnapshot,
    _fetch_management_prepaid,
    _resolve_team_id,
    fetch_grok_usage,
    format_usage_label,
    parse_billing_credits,
    parse_management_key_validation,
    parse_prepaid_balance,
    usage_severity,
)


class ParseBillingCreditsTests(unittest.TestCase):
    def test_credit_usage_percent(self) -> None:
        snapshot = parse_billing_credits(
            {"config": {"creditUsagePercent": 75.0, "currentPeriod": {"end": "2026-09-12T00:00:00Z"}}}
        )
        self.assertEqual(snapshot.remaining_percent, 25.0)
        self.assertEqual(snapshot.period_end, "2026-09-12T00:00:00Z")

    def test_credit_usage_percent_exhausted(self) -> None:
        snapshot = parse_billing_credits({"config": {"creditUsagePercent": 100.0}})
        self.assertEqual(snapshot.remaining_percent, 0.0)
        self.assertEqual(usage_severity(snapshot), "critical")

    def test_legacy_used_monthly_limit(self) -> None:
        snapshot = parse_billing_credits(
            {
                "config": {
                    "used": {"val": "2500"},
                    "monthlyLimit": {"val": "10000"},
                }
            }
        )
        self.assertEqual(snapshot.remaining_percent, 75.0)
        self.assertEqual(snapshot.source, "billing_credits_legacy")

    def test_missing_config(self) -> None:
        snapshot = parse_billing_credits({})
        self.assertIsNone(snapshot.remaining_percent)
        self.assertTrue(snapshot.error)


class ParsePrepaidBalanceTests(unittest.TestCase):
    def test_negative_total_is_remaining_balance(self) -> None:
        snapshot = parse_prepaid_balance({"total": {"val": "-1000"}})
        self.assertEqual(snapshot.remaining_usd, 10.0)

    def test_purchase_history_enables_percent(self) -> None:
        snapshot = parse_prepaid_balance(
            {
                "total": {"val": "-500"},
                "changes": [
                    {
                        "changeOrigin": "PURCHASE",
                        "amount": {"val": "-1000"},
                    }
                ],
            }
        )
        self.assertEqual(snapshot.remaining_usd, 5.0)
        self.assertEqual(snapshot.remaining_percent, 50.0)


class FormatUsageLabelTests(unittest.TestCase):
    def test_percent_label(self) -> None:
        label = format_usage_label(GrokUsageSnapshot(42.0, None, None, "billing_credits"))
        self.assertEqual(label, "Grok · 42% restant")

    def test_usd_label(self) -> None:
        label = format_usage_label(GrokUsageSnapshot(None, 12.5, None, "management_prepaid"))
        self.assertEqual(label, "Grok · $12.50 restants")


class ParseManagementKeyValidationTests(unittest.TestCase):
    def test_scope_team_uses_scope_id(self) -> None:
        team_id = parse_management_key_validation(
            {
                "scope": "SCOPE_TEAM",
                "scopeId": "65c1e471-205f-4566-9c5a-07198bcdf4ce",
                "teamId": "legacy-team-id",
            }
        )
        self.assertEqual(team_id, "65c1e471-205f-4566-9c5a-07198bcdf4ce")

    def test_fallback_team_id(self) -> None:
        team_id = parse_management_key_validation({"teamId": "c9a0c990-53e6-491e-8df7-b9f18e6983ac"})
        self.assertEqual(team_id, "c9a0c990-53e6-491e-8df7-b9f18e6983ac")


class ResolveTeamIdTests(unittest.TestCase):
    @patch("grok_usage.grok_team_id", return_value="env-team-123")
    def test_prefers_env_team_id(self, *_mocks: object) -> None:
        team_id, error = _resolve_team_id("mgmt-key", "inference-key")
        self.assertEqual(team_id, "env-team-123")
        self.assertIsNone(error)

    @patch("grok_usage.grok_team_id", return_value="")
    @patch("grok_usage._fetch_team_id_from_management")
    @patch("grok_usage._fetch_team_id_from_inference")
    def test_management_validation_before_inference(
        self,
        mock_inference: MagicMock,
        mock_management: MagicMock,
        *_mocks: object,
    ) -> None:
        mock_management.return_value = ("mgmt-team-456", None)

        team_id, error = _resolve_team_id("mgmt-key", "inference-key")

        self.assertEqual(team_id, "mgmt-team-456")
        self.assertIsNone(error)
        mock_inference.assert_not_called()

    @patch("grok_usage.grok_team_id", return_value="")
    @patch("grok_usage._fetch_team_id_from_management", return_value=(None, "HTTP 404"))
    @patch("grok_usage._fetch_team_id_from_inference", return_value=("api-team-789", None))
    def test_inference_fallback_camel_case(
        self,
        mock_inference: MagicMock,
        mock_management: MagicMock,
        *_mocks: object,
    ) -> None:
        team_id, error = _resolve_team_id("mgmt-key", "inference-key")

        self.assertEqual(team_id, "api-team-789")
        self.assertIsNone(error)
        mock_management.assert_called_once_with("mgmt-key")
        mock_inference.assert_called_once_with("inference-key")


class FetchManagementPrepaidTests(unittest.TestCase):
    @patch("grok_usage._resolve_team_id", return_value=("team-abc", None))
    @patch("grok_usage._fetch_json")
    def test_prepaid_url_uses_resolved_team(self, mock_fetch_json: MagicMock, *_mocks: object) -> None:
        mock_fetch_json.return_value = ({"total": {"val": "-1500"}}, None)

        snapshot = _fetch_management_prepaid("mgmt-key", "inference-key")

        mock_fetch_json.assert_called_once_with(
            "https://management-api.x.ai/v1/billing/teams/team-abc/prepaid/balance",
            "mgmt-key",
        )
        self.assertEqual(snapshot.remaining_usd, 15.0)
        self.assertEqual(snapshot.source, "management_prepaid")


class FetchGrokUsageTests(unittest.TestCase):
    @patch("grok_usage.grok_management_key", return_value="")
    @patch("grok_usage.grok_api_key", return_value="inference-key")
    @patch("grok_usage.requests.get")
    def test_fetch_billing_success(self, mock_get: MagicMock, *_mocks: object) -> None:
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = {"config": {"creditUsagePercent": 80.0}}

        snapshot = fetch_grok_usage()
        self.assertEqual(snapshot.remaining_percent, 20.0)
        mock_get.assert_called_once()

    @patch("grok_usage.grok_management_key", return_value="mgmt-key")
    @patch("grok_usage.grok_api_key", return_value="inference-key")
    @patch("grok_usage.requests.get")
    def test_fetch_prepaid_fallback(self, mock_get: MagicMock, *_mocks: object) -> None:
        billing_response = MagicMock()
        billing_response.ok = False
        billing_response.status_code = 404

        validation_response = MagicMock()
        validation_response.ok = True
        validation_response.json.return_value = {
            "scope": "SCOPE_TEAM",
            "scopeId": "team-xyz",
        }

        prepaid_response = MagicMock()
        prepaid_response.ok = True
        prepaid_response.json.return_value = {"total": {"val": "-2000"}}

        mock_get.side_effect = [billing_response, validation_response, prepaid_response]

        snapshot = fetch_grok_usage()
        self.assertEqual(snapshot.remaining_usd, 20.0)
        self.assertEqual(snapshot.source, "management_prepaid")
        self.assertEqual(mock_get.call_count, 3)

    @patch("grok_usage.grok_management_key", return_value="")
    @patch("grok_usage.grok_api_key", return_value="inference-key")
    @patch("grok_usage.requests.get")
    def test_fetch_http_error(self, mock_get: MagicMock, *_mocks: object) -> None:
        mock_get.return_value.ok = False
        mock_get.return_value.status_code = 403

        snapshot = fetch_grok_usage()
        self.assertIsNone(snapshot.remaining_percent)
        self.assertTrue(snapshot.error)


if __name__ == "__main__":
    unittest.main()
