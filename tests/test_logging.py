import json
import logging

import pytest

from apps.core.logging import ContextFilter, JsonFormatter, request_id_var
from apps.recommendations.models import Recommendation


@pytest.mark.django_db
class TestRequestID:
    def test_response_carries_a_generated_id(self, api_client):
        resp = api_client.get("/health/")
        rid = resp["X-Request-ID"]
        assert len(rid) == 32 and all(c in "0123456789abcdef" for c in rid)

    def test_upstream_id_is_reused(self, api_client):
        resp = api_client.get("/health/", HTTP_X_REQUEST_ID="nginx-abc-123")
        assert resp["X-Request-ID"] == "nginx-abc-123"

    def test_unsafe_upstream_id_is_replaced(self, api_client):
        resp = api_client.get("/health/", HTTP_X_REQUEST_ID="bad id\nwith newline" + "x" * 80)
        assert resp["X-Request-ID"] != "bad id"
        assert len(resp["X-Request-ID"]) == 32

    def test_context_is_reset_after_the_request(self, api_client):
        api_client.get("/health/", HTTP_X_REQUEST_ID="req-1")
        assert request_id_var.get() == "-"

    def test_access_log_line_has_id_user_and_duration(self, auth_client, user, caplog):
        with caplog.at_level(logging.INFO, logger="apps.requests"):
            auth_client.get(f"/users/{user.pk}/", HTTP_X_REQUEST_ID="req-42")
        record = next(r for r in caplog.records if r.name == "apps.requests")
        assert record.request_id == "req-42"
        assert record.user_id == str(user.pk)
        assert record.status == 200 and record.duration_ms >= 0
        assert f"/users/{user.pk}/" in record.getMessage()

    def test_health_is_not_access_logged(self, api_client, caplog):
        with caplog.at_level(logging.INFO, logger="apps.requests"):
            api_client.get("/health/")
        assert not [r for r in caplog.records if r.name == "apps.requests"]


@pytest.mark.django_db
class TestAudit:
    def test_401_403_429_are_audited(self, api_client, other_client, auth_client, user, caplog):
        with caplog.at_level(logging.WARNING, logger="apps.audit"):
            api_client.get(f"/users/{user.pk}/")  # 401
            other_client.get(f"/users/{user.pk}/")  # 403
            for _ in range(6):  # 5 allowed, 6th -> 429
                auth_client.post(f"/recommendations/{user.pk}/refresh/")
        events = [r.event for r in caplog.records if r.name == "apps.audit"]
        assert events == ["auth_failed", "forbidden", "throttled"]

    def test_ordinary_errors_are_not_audited(self, auth_client, caplog):
        with caplog.at_level(logging.WARNING, logger="apps.audit"):
            auth_client.post("/activity/", {"track_id": "x", "action": "dance"}, format="json")
        assert not [r for r in caplog.records if r.name == "apps.audit"]


@pytest.mark.django_db
class TestTaskCorrelation:
    def test_request_id_travels_into_the_task(self, auth_client, user, caplog):
        from apps.recommendations import tasks

        with caplog.at_level(logging.INFO, logger="apps.recommendations.tasks"):
            auth_client.post(f"/recommendations/{user.pk}/refresh/", HTTP_X_REQUEST_ID="req-77")
        ready = [r for r in caplog.records if "Recommendations ready" in r.getMessage()]
        assert ready and ready[0].request_id == "req-77"
        assert Recommendation.objects.get(user=user).status == "ready"
        assert tasks  # imported for side effects only

    def test_task_without_request_id_logs_a_dash(self, user, caplog):
        from apps.recommendations.tasks import refresh_user_recommendations

        with caplog.at_level(logging.INFO, logger="apps.recommendations.tasks"):
            refresh_user_recommendations.apply(args=[str(user.pk)]).get()
        ready = [r for r in caplog.records if "Recommendations ready" in r.getMessage()]
        assert ready and ready[0].request_id == "-"


class TestFormatters:
    def _record(self, **extra):
        record = logging.LogRecord(
            "apps.test", logging.INFO, __file__, 1, "hello %s", ("world",), None
        )
        for k, v in extra.items():
            setattr(record, k, v)
        ContextFilter().filter(record)
        return record

    def test_json_formatter_emits_parseable_line_with_context(self):
        token = request_id_var.set("req-json")
        try:
            out = json.loads(JsonFormatter().format(self._record(user_id="u1", status=200)))
        finally:
            request_id_var.reset(token)
        assert out["message"] == "hello world"
        assert out["request_id"] == "req-json"
        assert out["level"] == "INFO" and out["logger"] == "apps.test"
        assert out["user_id"] == "u1" and out["status"] == 200
        assert out["ts"].endswith("+00:00")

    def test_json_formatter_includes_exception_text(self):
        try:
            raise ValueError("kaboom")
        except ValueError:
            import sys

            record = logging.LogRecord(
                "apps.test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
            )
        ContextFilter().filter(record)
        out = json.loads(JsonFormatter().format(record))
        assert "ValueError: kaboom" in out["exception"]

    def test_text_format_from_settings_renders(self, settings):
        fmt = logging.Formatter(settings.LOGGING["formatters"]["text"]["format"])
        line = fmt.format(self._record())
        assert "rid=-" in line and "task=-" in line and "hello world" in line
