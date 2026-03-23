import src.core.register as register_module
from src.core.register import (
    ERROR_OTP_TIMEOUT_SECONDARY,
    PhaseContext,
    RegistrationEngine,
)
from src.services import EmailServiceType


class DummySettings:
    openai_client_id = "client-id"
    openai_auth_url = "https://auth.example.test"
    openai_token_url = "https://token.example.test"
    openai_redirect_uri = "https://callback.example.test"
    openai_scope = "openid profile email"


class FakeEmailService:
    def __init__(self, code):
        self.service_type = EmailServiceType.TEMPMAIL
        self.code = code
        self.calls = []

    def get_verification_code(self, **kwargs):
        self.calls.append(kwargs)
        return self.code


def _build_engine(monkeypatch, email_service):
    monkeypatch.setattr(register_module, "get_settings", lambda: DummySettings())
    return RegistrationEngine(email_service=email_service)


def test_phase_otp_secondary_uses_remaining_budget_from_start_timestamp(monkeypatch):
    email_service = FakeEmailService(code="654321")
    engine = _build_engine(monkeypatch, email_service)
    engine.email = "tester@example.com"
    engine.email_info = {"service_id": "svc-1"}

    monkeypatch.setattr(register_module.time, "time", lambda: 120.0)

    code, phase_result = engine._phase_otp_secondary(
        PhaseContext(otp_sent_at=77.0),
        started_at=100.0,
    )

    assert code == "654321"
    assert phase_result.success is True
    assert email_service.calls[0]["timeout"] == 100
    assert email_service.calls[0]["otp_sent_at"] == 77.0
    assert email_service.calls[0]["email"] == "tester@example.com"
    assert email_service.calls[0]["email_id"] == "svc-1"


def test_phase_otp_secondary_returns_dedicated_timeout_error_code(monkeypatch):
    email_service = FakeEmailService(code=None)
    engine = _build_engine(monkeypatch, email_service)
    engine.email = "tester@example.com"
    engine.email_info = {"service_id": "svc-1"}

    monkeypatch.setattr(register_module.time, "time", lambda: 120.0)

    code, phase_result = engine._phase_otp_secondary(
        PhaseContext(otp_sent_at=80.0),
        started_at=100.0,
    )

    assert code is None
    assert phase_result.success is False
    assert phase_result.error_code == ERROR_OTP_TIMEOUT_SECONDARY
    assert engine.phase_history[0].error_code == ERROR_OTP_TIMEOUT_SECONDARY


def test_advance_login_authorization_refreshes_otp_anchor_after_password_submit(monkeypatch):
    email_service = FakeEmailService(code=None)
    engine = _build_engine(monkeypatch, email_service)
    engine.oauth_start = object()
    engine._otp_sent_at = 10.0

    monkeypatch.setattr(register_module.time, "time", lambda: 456.0)
    monkeypatch.setattr(engine, "_init_session", lambda: True)
    monkeypatch.setattr(engine, "_start_oauth", lambda: True)
    monkeypatch.setattr(engine, "_get_device_id", lambda: True)
    monkeypatch.setattr(engine, "_try_reenter_login_flow", lambda: True)
    monkeypatch.setattr(
        engine,
        "_submit_login_password_step_and_get_continue_url",
        lambda: (True, "https://continue.example.test"),
    )

    seen_anchors = []

    def fake_get_verification_code():
        seen_anchors.append(engine._otp_sent_at)
        return None

    monkeypatch.setattr(engine, "_get_verification_code", fake_get_verification_code)

    workspace_id, callback_url = engine._advance_login_authorization()

    assert workspace_id is None
    assert callback_url is None
    assert engine._otp_sent_at == 456.0
    assert seen_anchors == [456.0]
