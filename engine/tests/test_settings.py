"""Tests for settings module."""
import pytest
import tempfile
import os

from process_intelligence_engine.settings import SettingsManager, AIProviderConfig


def test_default_config():
    mgr = SettingsManager()
    config = mgr.get_config()
    assert config['provider'] == 'ollama'
    assert config['base_url'] == 'http://localhost:11434'
    assert config['model'] == 'gemma4:e2b-mlx'


def test_update_config():
    mgr = SettingsManager()
    mgr.update_config({'provider': 'openai', 'base_url': 'https://api.openai.com', 'model': 'gpt-4'})
    config = mgr.get_config()
    assert config['provider'] == 'openai'
    assert config['base_url'] == 'https://api.openai.com'
    assert config['model'] == 'gpt-4'


def test_api_key_masked():
    mgr = SettingsManager()
    mgr.update_config({'api_key': 'sk-test123456789'})
    config = mgr.get_config()
    assert 'test1234' in config['api_key']
    assert '****' in config['api_key'] or '...' in config['api_key']


def test_provider_types():
    mgr = SettingsManager()
    for provider in ['ollama', 'openai', 'azure', 'custom']:
        mgr.update_config({'provider': provider})
        config = mgr.get_config()
        assert config['provider'] == provider


def test_persistence(tmp_path):
    # Create a temp config file
    config_path = tmp_path / 'settings.json'
    config_path.write_text('{"provider": "openai", "base_url": "https://test.com", "model": "gpt-3.5"}')
    
    # Monkey-patch the config path
    import process_intelligence_engine.settings.manager as mgr_module
    original_get_config_path = mgr_module.SettingsManager._get_config_path
    
    def mock_get_config_path(self):
        return str(config_path)
    
    mgr_module.SettingsManager._get_config_path = mock_get_config_path
    
    try:
        mgr = SettingsManager()
        config = mgr.get_config()
        assert config['provider'] == 'openai'
        assert config['base_url'] == 'https://test.com'
        assert config['model'] == 'gpt-3.5'
    finally:
        mgr_module.SettingsManager._get_config_path = original_get_config_path
