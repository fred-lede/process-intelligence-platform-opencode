"""Ollama API client for local LLM integration."""
from __future__ import annotations
import asyncio
from typing import Any, AsyncIterator, Optional
import aiohttp


class OllamaClient:
    """Client for Ollama REST API."""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma4:e2b-mlx"):
        self.base_url = base_url
        self.model = model
    
    async def chat(
        self,
        messages: list[dict[str, str]],
        stream: bool = False,
        options: dict[str, Any] | None = None,
    ) -> str | AsyncIterator[str]:
        """Send chat messages to Ollama."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": options or {},
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/api/chat", json=payload) as resp:
                if stream:
                    return self._stream_response(resp)
                result = await resp.json()
                return result["message"]["content"]
    
    async def _stream_response(self, resp: aiohttp.ClientResponse) -> AsyncIterator[str]:
        async for line in resp.content:
            if line:
                import json
                data = json.loads(line)
                if "message" in data and "content" in data["message"]:
                    yield data["message"]["content"]
    
    async def generate(self, prompt: str, stream: bool = False) -> str | AsyncIterator[str]:
        """Simple text generation."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/api/generate", json=payload) as resp:
                if stream:
                    return self._stream_generate(resp)
                result = await resp.json()
                return result["response"]
    
    async def _stream_generate(self, resp: aiohttp.ClientResponse) -> AsyncIterator[str]:
        async for line in resp.content:
            if line:
                import json
                data = json.loads(line)
                if "response" in data:
                    yield data["response"]
    
    async def list_models(self) -> list[dict]:
        """List available models."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/api/tags") as resp:
                result = await resp.json()
                return result.get("models", [])
    
    async def health_check(self) -> bool:
        """Check if Ollama is running."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status == 200
        except Exception:
            return False


# Singleton instance
_ollama_client: Optional[OllamaClient] = None

def get_ollama_client() -> OllamaClient:
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client
