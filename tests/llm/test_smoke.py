"""Smoke tests against the real Gemini API — cost tokens.

Run explicitly: python -m pytest tests/llm -m llm
Validates the API key in .env and the configured model IDs.
"""

import numpy as np
import pytest

from libkb.llm.client import get_llm

pytestmark = pytest.mark.llm


def test_generate_returns_text_and_usage():
    result = get_llm().generate("Reply with exactly the word: OK")
    assert result.text is not None
    assert "OK" in result.text.upper()
    assert result.usage is not None
    assert result.usage.input_tokens > 0


def test_embed_returns_normalized_vectors():
    vectors = get_llm().embed(["xin chào thư viện", "hello library"])
    assert vectors.shape[0] == 2
    assert vectors.shape[1] >= 128
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-3)
