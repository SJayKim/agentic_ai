"""
Config Layer - 설정 및 프롬프트 관리

이 레이어의 역할:
- YAML 설정 파일 로드 및 관리
- 프롬프트 템플릿 로드
- 런타임 설정 변경 지원

현재 구현:
- ConfigLoader: settings.yaml 로드, dot notation 지원
- PromptLoader: 프롬프트 YAML 파일 로드
"""

from .config_loader import ConfigLoader
from .prompt_loader import PromptLoader

__all__ = ["ConfigLoader", "PromptLoader"]
