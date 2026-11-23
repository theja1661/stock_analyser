from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from analyzer.llm_analysis import (
    GeminiProvider,
    OpenRouterProvider,
    PROVIDERS,
    RetryableError,
    StockAnalysis,
)


class OpenRouterProviderTests(unittest.TestCase):
    def cfg(self, **overrides):
        llm = {
            "provider": "openrouter",
            "model": "openrouter/free",
            "api_key_env": "TEST_OPENROUTER_API_KEY",
            "max_document_chars": 60000,
            "max_pdf_chars": 40000,
            "temperature": 0.2,
            "timeout_seconds": 60,
        }
        llm.update(overrides)
        return {"llm": llm, "network": {"ca_bundle": None}}

    def provider_with_mock_client(self, cfg=None):
        cfg = cfg or self.cfg()
        mock_openai = SimpleNamespace(
            OpenAI=Mock(
                return_value=SimpleNamespace(
                    chat=SimpleNamespace(completions=SimpleNamespace(create=Mock()))
                )
            )
        )
        with patch.dict(sys.modules, {"openai": mock_openai}):
            provider = OpenRouterProvider(cfg)
        return provider, mock_openai.OpenAI.return_value

    def setUp(self):
        os.environ["TEST_OPENROUTER_API_KEY"] = "test-key"

    def tearDown(self):
        os.environ.pop("TEST_OPENROUTER_API_KEY", None)

    def test_provider_registration(self):
        self.assertIs(PROVIDERS["gemini"], GeminiProvider)
        self.assertIs(PROVIDERS["openrouter"], OpenRouterProvider)

    def test_missing_api_key(self):
        os.environ.pop("TEST_OPENROUTER_API_KEY", None)
        mock_openai = SimpleNamespace(OpenAI=Mock())
        with patch.dict(sys.modules, {"openai": mock_openai}):
            with self.assertRaisesRegex(RuntimeError, "TEST_OPENROUTER_API_KEY"):
                OpenRouterProvider(self.cfg())

    def test_txt_document_processing(self):
        provider, _ = self.provider_with_mock_client()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quarter.txt"
            path.write_text("Quarterly revenue grew 10%.", encoding="utf-8")
            prompt = provider._documents_prompt([path])
        self.assertIn("--- Document: quarter.txt ---", prompt)
        self.assertIn("revenue grew 10%", prompt)

    def test_md_document_processing(self):
        provider, _ = self.provider_with_mock_client()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transcript.md"
            path.write_text("# Guidance\nMargins may improve.", encoding="utf-8")
            prompt = provider._documents_prompt([path])
        self.assertIn("Margins may improve.", prompt)

    def test_pdf_text_extraction(self):
        provider, _ = self.provider_with_mock_client()
        fake_reader = SimpleNamespace(pages=[
            SimpleNamespace(extract_text=lambda: "Revenue 100"),
            SimpleNamespace(extract_text=lambda: "Profit 20"),
        ])
        fake_pypdf = SimpleNamespace(PdfReader=Mock(return_value=fake_reader))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quarter.pdf"
            path.write_bytes(b"%PDF")
            with patch.dict(sys.modules, {"pypdf": fake_pypdf}):
                text = provider._extract_pdf_text(path)
        self.assertIn("Revenue 100", text)
        self.assertIn("Profit 20", text)

    def test_scanned_pdf_clear_error(self):
        provider, _ = self.provider_with_mock_client()
        fake_reader = SimpleNamespace(pages=[
            SimpleNamespace(extract_text=lambda: "")
        ])
        fake_pypdf = SimpleNamespace(PdfReader=Mock(return_value=fake_reader))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scanned.pdf"
            path.write_bytes(b"%PDF")
            with patch.dict(sys.modules, {"pypdf": fake_pypdf}):
                with self.assertRaisesRegex(RuntimeError, "OCR is required"):
                    provider._extract_pdf_text(path)

    def test_invalid_json_handled(self):
        provider, client = self.provider_with_mock_client()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
        )
        with self.assertRaisesRegex(RuntimeError, "Invalid JSON"):
            provider.generate("prompt", [])

    def test_valid_json_converted_to_stock_analysis(self):
        provider, client = self.provider_with_mock_client()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='''{
                "thesis": "Strong growth",
                "risks": ["Competition"],
                "red_flags": [],
                "guidance_summary": "No guidance given",
                "conviction": 6
            }'''))]
        )
        result = provider.generate("prompt", [])
        self.assertEqual(StockAnalysis.model_validate(result).conviction, 6)

    def test_retryable_http_errors(self):
        provider, client = self.provider_with_mock_client()
        error = RuntimeError("rate limited")
        error.status_code = 429
        client.chat.completions.create.side_effect = error
        with self.assertRaises(RetryableError):
            provider.generate("prompt", [])


if __name__ == "__main__":
    unittest.main()
