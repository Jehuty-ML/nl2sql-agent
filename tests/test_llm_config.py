from app.config import PROVIDER_DEFAULTS, Settings


def test_provider_aliases():
    s = Settings(llm_provider="qwen", dashscope_api_key="x")
    assert s.normalized_provider() == "dashscope"


def test_resolve_dashscope():
    s = Settings(llm_provider="dashscope", dashscope_api_key="sk-test", llm_api_key="")
    llm = s.resolve_llm()
    assert llm["enabled"] is True
    assert llm["provider"] == "dashscope"
    assert llm["model"] == PROVIDER_DEFAULTS["dashscope"]["model"]
    assert "dashscope.aliyuncs.com" in str(llm["base_url"])


def test_resolve_deepseek():
    s = Settings(
        llm_provider="deepseek",
        deepseek_api_key="sk-ds",
        deepseek_model="deepseek-chat",
        llm_api_key="",
    )
    llm = s.resolve_llm()
    assert llm["provider"] == "deepseek"
    assert llm["api_key"] == "sk-ds"
    assert llm["enabled"] is True


def test_resolve_ark():
    s = Settings(llm_provider="ark", ark_api_key="ark-key", llm_api_key="")
    llm = s.resolve_llm()
    assert llm["provider"] == "ark"
    assert "volces.com" in str(llm["base_url"])
    assert llm["enabled"] is True


def test_resolve_ollama_without_real_key():
    s = Settings(
        llm_provider="ollama",
        ollama_base_url="http://127.0.0.1:11434/v1",
        ollama_model="qwen2.5:14b",
        llm_api_key="",
    )
    llm = s.resolve_llm()
    assert llm["enabled"] is True
    assert llm["provider"] == "ollama"


def test_disabled_without_key():
    s = Settings(
        llm_provider="dashscope",
        dashscope_api_key="",
        llm_api_key="",
    )
    assert s.resolve_llm()["enabled"] is False
