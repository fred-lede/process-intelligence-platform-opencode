"""Test AI (Ollama) IPC handlers."""

import pytest

from process_intelligence_engine.main import handle_request


def test_ai_health_returns_bool():
    result = handle_request("ai/health", {})
    assert "healthy" in result
    assert isinstance(result["healthy"], bool)


def test_ai_models_returns_success_flag():
    result = handle_request("ai/models", {})
    assert "success" in result
    if result["success"]:
        assert "models" in result
    else:
        assert "error" in result


def test_ai_chat_returns_success_flag():
    result = handle_request("ai/chat", {"messages": [{"role": "user", "content": "hi"}]})
    assert "success" in result
    if result["success"]:
        assert "response" in result
    else:
        assert "error" in result


def test_ai_chat_with_model():
    result = handle_request("ai/chat", {
        "messages": [{"role": "user", "content": "hi"}],
        "model": "gemma4:e2b-mlx",
    })
    assert "success" in result


def test_ai_unknown_method_raises():
    with pytest.raises(ValueError, match="Unknown method"):
        handle_request("ai/unknown", {})
