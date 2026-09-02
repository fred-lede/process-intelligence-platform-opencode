"""AI provider settings management."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional


ProviderType = Literal['ollama', 'openai', 'azure', 'custom']


@dataclass
class AIProviderConfig:
    """Configuration for an AI provider."""
    provider: ProviderType = 'ollama'
    base_url: str = 'http://localhost:11434'
    api_key: str = ''
    model: str = 'gemma4:e2b-mlx'
    enabled: bool = True


class SettingsManager:
    """Manage application settings."""
    
    def __init__(self):
        self._config = AIProviderConfig()
        self._load()
    
    def _get_config_path(self) -> str:
        import os
        return os.path.expanduser('~/.process_intelligence_platform/settings.json')
    
    def _load(self) -> None:
        """Load settings from file."""
        import json
        import os
        path = self._get_config_path()
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    self._config = AIProviderConfig(**data)
            except Exception:
                pass
    
    def _save(self) -> None:
        """Save settings to file."""
        import json
        import os
        path = self._get_config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self._config.__dict__, f, indent=2)
    
    def get_config(self) -> dict:
        """Get current settings (sensitive data masked)."""
        config = self._config.__dict__.copy()
        if config.get('api_key'):
            config['api_key'] = config['api_key'][:4] + '...' + config['api_key'][-4:] if len(config['api_key']) > 8 else '****'
        return config
    
    def update_config(self, updates: dict) -> None:
        """Update settings."""
        for key, value in updates.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
        self._save()
    
    def test_connection(self) -> dict:
        """Test connection to the configured provider."""
        import asyncio
        try:
            if self._config.provider == 'ollama':
                from ..ai.ollama_client import OllamaClient
                client = OllamaClient(
                    base_url=self._config.base_url,
                    model=self._config.model
                )
                is_healthy = asyncio.run(client.health_check())
                return {"success": is_healthy}
            else:
                import aiohttp
                url = f"{self._config.base_url.rstrip('/')}/models"
                headers = {"Authorization": f"Bearer {self._config.api_key}"} if self._config.api_key else {}
                async def _check() -> bool:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            return resp.status == 200
                is_healthy = asyncio.run(_check())
                return {"success": is_healthy}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Singleton instance
_settings_manager: Optional[SettingsManager] = None


def get_settings_manager() -> SettingsManager:
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager
