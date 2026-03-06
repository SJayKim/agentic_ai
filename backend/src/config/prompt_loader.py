"""
프롬프트 로더 - YAML 프롬프트 파일 로드 및 관리
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class PromptLoader:
    """프롬프트 파일 로더"""
    
    _instance: Optional["PromptLoader"] = None
    _prompts: Dict[str, Dict[str, Any]] = {}
    _prompts_dir: Optional[Path] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._prompts_dir:
            self._prompts_dir = self._get_prompts_dir()
            self._load_all_prompts()
    
    def _get_prompts_dir(self) -> Path:
        """프롬프트 디렉토리 경로 반환"""
        env_path = os.getenv("SDP_PROMPTS_PATH")
        if env_path:
            return Path(env_path)
        
        # 기본 경로: 프로젝트 루트/prompts/
        # src/config/prompt_loader.py → src → project_root
        project_root = Path(__file__).parent.parent.parent
        return project_root / "prompts"
    
    def _load_all_prompts(self) -> None:
        """모든 프롬프트 파일 로드"""
        if not self._prompts_dir.exists():
            return
        
        for prompt_file in self._prompts_dir.glob("*.yaml"):
            prompt_name = prompt_file.stem
            try:
                with open(prompt_file, "r", encoding="utf-8") as f:
                    self._prompts[prompt_name] = yaml.safe_load(f)
            except Exception as e:
                print(f"Warning: Failed to load prompt {prompt_file}: {e}")
    
    def get_prompt(self, name: str) -> Dict[str, Any]:
        """프롬프트 설정 반환"""
        return self._prompts.get(name, {})
    
    def get_system_prompt(self, name: str) -> str:
        """시스템 프롬프트 문자열 반환"""
        prompt_config = self.get_prompt(name)
        return prompt_config.get("system_prompt", "")
    
    def get_template(self, name: str, template_name: str) -> str:
        """특정 템플릿 반환"""
        prompt_config = self.get_prompt(name)
        templates = prompt_config.get("templates", {})
        return templates.get(template_name, "")
    
    def get_default(self, name: str, key: str, fallback: Any = None) -> Any:
        """기본값 반환"""
        prompt_config = self.get_prompt(name)
        defaults = prompt_config.get("defaults", {})
        return defaults.get(key, fallback)
    
    def reload(self) -> None:
        """프롬프트 다시 로드"""
        self._prompts.clear()
        self._load_all_prompts()


# 싱글톤 인스턴스
prompts = PromptLoader()
