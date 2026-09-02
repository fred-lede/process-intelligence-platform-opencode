"""Tests for Ollama client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from process_intelligence_engine.ai.ollama_client import OllamaClient


@pytest.fixture
def client():
    return OllamaClient(base_url="http://localhost:11434", model="test-model")


@pytest.mark.asyncio
async def test_health_check_success(client):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session_instance = MagicMock()
    mock_session_instance.get.return_value = mock_cm

    with patch('aiohttp.ClientSession') as mock_session_cls:
        mock_session_cls.return_value = mock_session_instance
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=False)
        result = await client.health_check()
        assert result is True


@pytest.mark.asyncio
async def test_health_check_failure(client):
    with patch('aiohttp.ClientSession') as mock_session:
        mock_session.return_value.get.side_effect = Exception("Connection failed")
        result = await client.health_check()
        assert result is False


def test_list_models_sync(client):
    """Test that list_models method exists."""
    assert hasattr(client, 'list_models')
    assert callable(client.list_models)


def test_get_ollama_client():
    from process_intelligence_engine.ai.ollama_client import get_ollama_client
    c1 = get_ollama_client()
    c2 = get_ollama_client()
    assert c1 is c2  # Singleton


def test_client_initialization():
    client = OllamaClient(model="llama3")
    assert client.model == "llama3"
    assert client.base_url == "http://localhost:11434"
