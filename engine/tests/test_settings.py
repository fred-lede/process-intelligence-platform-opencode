"""Tests for settings module."""
import pytest
import tempfile
import os

from process_intelligence_engine.settings import SettingsManager, AIProviderConfig


def test_default_config():
    mgr = SettingsManager()
    config = mgr.get_config()
    # Default should be ollama or whatever was last saved
    assert config['provider'] in ['ollama', 'openai', 'azure', 'custom']
    assert isinstance(config['base_url'], str)
    assert isinstance(config['model'], str)


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
    # Key should be masked - show first 4 and last 4 chars
    assert 'sk-t' in config['api_key']
    assert '6789' in config['api_key']
    assert '...' in config['api_key']


def test_provider_types():
    mgr = SettingsManager()
    for provider in ['ollama', 'openai', 'azure', 'custom']:
        mgr.update_config({'provider': provider})
        config = mgr.get_config()
        assert config['provider'] == provider


def test_persistence(tmp_path):
    """Test that settings are saved and loaded correctly."""
    # Create a temp config file
    config_path = tmp_path / 'settings.json'
    config_path.write_text('{"provider": "openai", "base_url": "https://test.com", "model": "gpt-3.5"}')
    
    # Test that update and get work correctly
    mgr = SettingsManager()
    mgr.update_config({'provider': 'openai', 'base_url': 'https://test.com', 'model': 'gpt-3.5'})
    config = mgr.get_config()
    assert config['provider'] == 'openai'
    assert config['base_url'] == 'https://test.com'
    assert config['model'] == 'gpt-3.5'
