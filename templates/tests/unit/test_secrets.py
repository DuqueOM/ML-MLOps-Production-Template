"""Unit tests for ``common_utils.secrets``.

Closes external-feedback gap 5.1 (May 2026): the secrets resolver
enforces invariants D-17 (never log values) and D-18 (no os.environ
fallback in staging/production) but had ZERO unit-test coverage.
This file exercises every resolution branch + the negative cases
that prove the invariants hold.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

import pytest

import common_utils.secrets as secrets
from common_utils.secrets import (
    SecretBackendError,
    SecretNotFoundError,
    _detect_cloud,
    _detect_environment,
    _load_dotenv_local,
    get_secret,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with a clean environment + cleared dotenv cache."""
    for var in (
        "ENV",
        "CLOUD_PROVIDER",
        "GITHUB_ACTIONS",
        "KUBERNETES_SERVICE_HOST",
        "POD_NAMESPACE",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "GCE_METADATA_HOST",
        "GCP_PROJECT_ID",
    ):
        monkeypatch.delenv(var, raising=False)
    _load_dotenv_local.cache_clear()


# ---------------------------------------------------------------------------
# _detect_environment
# ---------------------------------------------------------------------------
class TestDetectEnvironment:
    @pytest.mark.parametrize(
        "env_value,expected",
        [
            ("local", "local"),
            ("dev", "local"),
            ("development", "local"),
            ("ci", "ci"),
            ("test", "ci"),
            ("staging", "staging"),
            ("stage", "staging"),
            ("production", "production"),
            ("prod", "production"),
        ],
    )
    def test_explicit_env_var(self, monkeypatch: pytest.MonkeyPatch, env_value: str, expected: str) -> None:
        monkeypatch.setenv("ENV", env_value)
        assert _detect_environment() == expected

    def test_github_actions_heuristic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        assert _detect_environment() == "ci"

    def test_kubernetes_namespace_with_prod(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
        monkeypatch.setenv("POD_NAMESPACE", "fraud-prod")
        assert _detect_environment() == "production"

    def test_kubernetes_namespace_without_prod(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
        monkeypatch.setenv("POD_NAMESPACE", "fraud-staging")
        assert _detect_environment() == "staging"

    def test_default_is_local(self) -> None:
        assert _detect_environment() == "local"


# ---------------------------------------------------------------------------
# _detect_cloud
# ---------------------------------------------------------------------------
class TestDetectCloud:
    @pytest.mark.parametrize("explicit", ["aws", "AWS", "gcp", "GCP"])
    def test_explicit_provider_wins(self, monkeypatch: pytest.MonkeyPatch, explicit: str) -> None:
        monkeypatch.setenv("CLOUD_PROVIDER", explicit)
        assert _detect_cloud() == explicit.lower()

    def test_aws_via_irsa(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AWS_WEB_IDENTITY_TOKEN_FILE", "/var/run/secrets/eks.amazonaws.com/serviceaccount/token")
        assert _detect_cloud() == "aws"

    def test_gcp_via_metadata_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GCE_METADATA_HOST", "metadata.google.internal")
        assert _detect_cloud() == "gcp"

    def test_unknown_when_no_signal(self) -> None:
        assert _detect_cloud() == "unknown"


# ---------------------------------------------------------------------------
# .env.local + local backend
# ---------------------------------------------------------------------------
class TestLocalBackend:
    def test_dotenv_parsing_strips_quotes_and_whitespace(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            'API_KEY = "sk_test_123"\n'
            "DB_PASSWORD = 'pw'\n"
            "BARE_VAL=plain\n"
            "# COMMENT=ignored\n"
            "MALFORMED_NO_EQUALS\n"
        )
        monkeypatch.chdir(tmp_path)
        _load_dotenv_local.cache_clear()
        assert _load_dotenv_local() == {
            "API_KEY": "sk_test_123",
            "DB_PASSWORD": "pw",
            "BARE_VAL": "plain",
        }

    def test_local_resolves_from_dotenv(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        (tmp_path / ".env.local").write_text("API_KEY=local_value\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ENV", "local")
        _load_dotenv_local.cache_clear()
        assert get_secret("API_KEY") == "local_value"

    def test_local_falls_back_to_os_environ(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ENV", "local")
        monkeypatch.setenv("API_KEY", "from_environ")
        _load_dotenv_local.cache_clear()
        assert get_secret("API_KEY") == "from_environ"

    def test_local_miss_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ENV", "local")
        _load_dotenv_local.cache_clear()
        with pytest.raises(SecretNotFoundError):
            get_secret("UNKNOWN_KEY")

    def test_local_miss_with_default_returns_default(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ENV", "local")
        _load_dotenv_local.cache_clear()
        assert get_secret("MISSING", default="fallback") == "fallback"


# ---------------------------------------------------------------------------
# CI backend
# ---------------------------------------------------------------------------
class TestCIBackend:
    def test_ci_resolves_from_environ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENV", "ci")
        monkeypatch.setenv("API_KEY", "ci_value")
        assert get_secret("API_KEY") == "ci_value"

    def test_ci_miss_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENV", "ci")
        with pytest.raises(SecretNotFoundError):
            get_secret("MISSING")


# ---------------------------------------------------------------------------
# Staging / production — D-18 invariant
# ---------------------------------------------------------------------------
class TestProductionInvariants:
    """The D-18 invariant: staging/production NEVER fall through to os.environ.

    These tests are the canonical guarantees the secrets module ships.
    """

    @pytest.mark.parametrize("env_label", ["staging", "production"])
    def test_unknown_cloud_in_non_local_raises(
        self, monkeypatch: pytest.MonkeyPatch, env_label: str
    ) -> None:
        monkeypatch.setenv("ENV", env_label)
        # No CLOUD_PROVIDER, no IRSA, no GCP metadata.
        # Even if API_KEY is in os.environ, get_secret MUST refuse it.
        monkeypatch.setenv("API_KEY", "this_must_not_be_returned")
        with pytest.raises(SecretBackendError, match="CLOUD_PROVIDER not detected"):
            get_secret("API_KEY")

    def test_aws_backend_invoked_when_cloud_aws(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("CLOUD_PROVIDER", "aws")
        called = {}

        def _fake_get_aws(key: str, namespace: str | None) -> str:
            called["key"] = key
            called["namespace"] = namespace
            return "from_aws"

        monkeypatch.setattr(secrets, "_get_aws", _fake_get_aws)
        assert get_secret("API_KEY", namespace="fraud") == "from_aws"
        assert called == {"key": "API_KEY", "namespace": "fraud"}

    def test_gcp_backend_invoked_when_cloud_gcp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("CLOUD_PROVIDER", "gcp")
        called = {}

        def _fake_get_gcp(key: str, namespace: str | None) -> str:
            called["key"] = key
            called["namespace"] = namespace
            return "from_gcp"

        monkeypatch.setattr(secrets, "_get_gcp", _fake_get_gcp)
        assert get_secret("API_KEY", namespace="fraud") == "from_gcp"
        assert called == {"key": "API_KEY", "namespace": "fraud"}

    def test_default_returned_on_miss_in_staging(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENV", "staging")
        monkeypatch.setenv("CLOUD_PROVIDER", "aws")
        monkeypatch.setattr(
            secrets, "_get_aws", lambda *a, **kw: (_ for _ in ()).throw(SecretNotFoundError("miss"))
        )
        assert get_secret("MISSING", default="fallback") == "fallback"


# ---------------------------------------------------------------------------
# D-17 invariant — value never logged
# ---------------------------------------------------------------------------
class TestD17NeverLogValue:
    """D-17: the secret value MUST NOT appear in any log record."""

    def test_value_never_in_log_messages(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        sentinel = "TOPSECRET-SHOULD-NEVER-LEAK-9b3a7f"
        (tmp_path / ".env.local").write_text(f"API_KEY={sentinel}\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ENV", "local")
        _load_dotenv_local.cache_clear()

        with caplog.at_level(logging.DEBUG, logger="common_utils.secrets"):
            value = get_secret("API_KEY")

        assert value == sentinel
        # The sentinel must not appear in ANY captured record's
        # message, args, OR the structured `extra` payload.
        for record in caplog.records:
            assert sentinel not in record.getMessage()
            for arg in record.args or ():
                assert sentinel not in str(arg)
            # `extra` is merged into __dict__; check there too.
            for key, val in record.__dict__.items():
                if key in {"args", "msg", "message"}:
                    continue
                assert sentinel not in str(val), (
                    f"Secret leaked into log record field {key!r}: {val!r}"
                )
