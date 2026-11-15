import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from backend.app import main
from backend.app.schemas import AnalysisCategory, MarketAnalysisRequest


def make_request(host: str) -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/analysis",
        "headers": [],
        "query_string": b"",
        "client": (host, 8000),
        "server": ("localhost", 8000),
        "scheme": "http",
    })


def make_payload() -> MarketAnalysisRequest:
    return MarketAnalysisRequest(
        listing_count=3,
        median_asking_price_ngn=300000,
        price_reductions=1,
        engagement_records=2,
        categories=[
            AnalysisCategory(
                name="Phones",
                listing_count=3,
                median_asking_price_ngn=300000,
                price_reductions=1,
                engagement_records=2,
            )
        ],
    )


class AnalysisEndpointTests(unittest.TestCase):
    def test_analysis_requires_backend_configuration(self) -> None:
        with (
            patch.object(main, "OPENAI_API_KEY", ""),
            patch.object(main, "OPENAI_MODEL", ""),
        ):
            with self.assertRaises(HTTPException) as error:
                main.analyze_market(make_payload(), make_request("127.0.0.1"))
        self.assertEqual(error.exception.status_code, 503)

    def test_analysis_rejects_remote_requests_by_default(self) -> None:
        with patch.object(main, "ALLOW_REMOTE_AI_ANALYSIS", False):
            with self.assertRaises(HTTPException) as error:
                main.analyze_market(make_payload(), make_request("203.0.113.8"))
        self.assertEqual(error.exception.status_code, 403)

    def test_analysis_sends_only_aggregates_and_returns_model_output(self) -> None:
        captured: dict[str, object] = {}

        class FakeResponses:
            def create(self, **kwargs: object) -> SimpleNamespace:
                captured.update(kwargs)
                return SimpleNamespace(output_text="Observed: 3 phone listings.")

        class FakeOpenAI:
            def __init__(self, **_: object) -> None:
                self.responses = FakeResponses()

        with (
            patch.object(main, "OPENAI_API_KEY", "test-key"),
            patch.object(main, "OPENAI_MODEL", "test-model"),
            patch.object(main, "ALLOW_REMOTE_AI_ANALYSIS", False),
            patch.object(main, "OpenAI", FakeOpenAI),
        ):
            result = main.analyze_market(make_payload(), make_request("127.0.0.1"))

        submitted = json.loads(str(captured["input"]))
        self.assertEqual(result["analysis"], "Observed: 3 phone listings.")
        self.assertEqual(result["model"], "test-model")
        self.assertFalse(captured["store"])
        self.assertEqual(submitted["listing_count"], 3)
        self.assertNotIn("title", submitted)
        self.assertNotIn("location", submitted)


if __name__ == "__main__":
    unittest.main()
