"""
LLM Provider Factory - LangChain ChatModel 생성

config/settings.yaml 기반으로 적절한 LLM Provider 동적 생성.
지원: Google (Gemini), OpenAI, Anthropic

각 에이전트 노드(router, actor, evaluator, reflection)별로
독립된 LLM 인스턴스를 생성하여 context 오염을 방지합니다.
"""

import os
from typing import Optional, Dict, Any
from enum import Enum

from langchain_core.language_models.chat_models import BaseChatModel

from src.config.config_loader import ConfigLoader


class LLMProviderType(str, Enum):
    """지원하는 LLM Provider 종류"""
    GOOGLE = "google"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


def get_llm(
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **kwargs
) -> BaseChatModel:
    """
    LangChain ChatModel 생성
    
    config/settings.yaml에서 설정을 로드하고,
    인자로 전달된 값이 있으면 오버라이드.
    
    Args:
        provider: "google", "openai", "anthropic"
        model_name: 모델 이름
        temperature: 생성 온도
        max_tokens: 최대 토큰 수
        **kwargs: 추가 설정
        
    Returns:
        LangChain BaseChatModel 인스턴스
        
    Usage:
        llm = get_llm()  # config에서 자동 로드
        llm = get_llm(provider="openai", model_name="gpt-4o")  # 오버라이드
    """
    config = ConfigLoader()
    
    # 설정 로드 (인자 우선)
    provider = provider or config.get("llm.provider", "google")
    model_name = model_name or config.get("llm.model_name", "gemini-2.5-flash")
    temperature = temperature if temperature is not None else config.get("llm.temperature", 0.7)
    max_tokens = max_tokens or config.get("llm.max_tokens", 4096)
    
    # Provider별 ChatModel 생성
    if provider == LLMProviderType.GOOGLE or provider == "google":
        return _create_google_llm(model_name, temperature, max_tokens, **kwargs)
    elif provider == LLMProviderType.OPENAI or provider == "openai":
        return _create_openai_llm(model_name, temperature, max_tokens, **kwargs)
    elif provider == LLMProviderType.ANTHROPIC or provider == "anthropic":
        return _create_anthropic_llm(model_name, temperature, max_tokens, **kwargs)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def get_node_llm(node_name: str) -> BaseChatModel:
    """
    특정 에이전트 노드 전용 LLM 인스턴스 생성
    
    각 노드(router, actor, evaluator, reflection, direct_answer)별로
    독립된 설정을 로드하여 별도의 LLM 인스턴스를 반환합니다.
    노드별 설정이 없으면 기본(llm) 설정으로 fallback합니다.
    
    Args:
        node_name: 노드 이름 ("router", "actor", "evaluator", "reflection", "direct_answer")
        
    Returns:
        해당 노드 전용 LangChain BaseChatModel 인스턴스
    """
    config = ConfigLoader()
    
    # 노드별 설정 로드 (없으면 기본값으로 fallback)
    provider = config.get(f"llm.{node_name}.provider", config.get("llm.provider", "google"))
    model_name = config.get(f"llm.{node_name}.model_name", config.get("llm.model_name", "gemini-2.5-flash"))
    temperature = config.get(f"llm.{node_name}.temperature", config.get("llm.temperature", 0.7))
    max_tokens = config.get(f"llm.{node_name}.max_tokens", config.get("llm.max_tokens", 4096))
    
    print(f"[LLM] Creating {node_name} LLM: {model_name} (temp={temperature}, max_tokens={max_tokens})")
    
    return get_llm(
        provider=provider,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _create_google_llm(
    model_name: str,
    temperature: float,
    max_tokens: int,
    **kwargs
) -> BaseChatModel:
    """Google Gemini ChatModel 생성"""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        raise ImportError("langchain-google-genai 패키지가 필요합니다: pip install langchain-google-genai")
    
    api_key = kwargs.get("api_key") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY 환경변수가 필요합니다.")
    
    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=temperature,
        max_output_tokens=max_tokens,
        google_api_key=api_key,
        convert_system_message_to_human=True,  # Gemini 호환성
    )


def _create_openai_llm(
    model_name: str,
    temperature: float,
    max_tokens: int,
    **kwargs
) -> BaseChatModel:
    """OpenAI ChatModel 생성"""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise ImportError("langchain-openai 패키지가 필요합니다: pip install langchain-openai")
    
    api_key = kwargs.get("api_key") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 환경변수가 필요합니다.")
    
    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=api_key,
    )


def _create_anthropic_llm(
    model_name: str,
    temperature: float,
    max_tokens: int,
    **kwargs
) -> BaseChatModel:
    """Anthropic ChatModel 생성"""
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        raise ImportError("langchain-anthropic 패키지가 필요합니다: pip install langchain-anthropic")
    
    api_key = kwargs.get("api_key") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY 환경변수가 필요합니다.")
    
    return ChatAnthropic(
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=api_key,
    )


# 편의 함수
def get_default_llm() -> BaseChatModel:
    """기본 설정으로 LLM 생성"""
    return get_llm()


def get_llm_from_config(config_key: str = "llm", config_path: Optional[str] = None) -> BaseChatModel:
    """
    특정 설정 섹션에서 LLM 생성
    
    여러 LLM 설정을 사용할 때 유용.
    예: llm.actor, llm.evaluator 등
    
    Args:
        config_key: 설정 섹션 키 (예: "llm", "llm.actor")
        config_path: 설정 파일 경로 (None이면 기본 settings.yaml)
    
    Returns:
        LangChain BaseChatModel 인스턴스
    """
    config = ConfigLoader(config_path) if config_path else ConfigLoader()
    
    provider = config.get(f"{config_key}.provider", "google")
    model_name = config.get(f"{config_key}.model_name", "gemini-2.5-flash")
    temperature = config.get(f"{config_key}.temperature", 0.7)
    max_tokens = config.get(f"{config_key}.max_tokens", 4096)
    
    return get_llm(
        provider=provider,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
    )
