"""
설정 로더 - YAML 설정 파일 로드 및 관리
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class ConfigLoader:
    """설정 파일 로더"""
    
    _instance: Optional["ConfigLoader"] = None
    _config: Optional[Dict[str, Any]] = None
    _config_path_override: Optional[str] = None
    
    def __new__(cls, config_path: Optional[str] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config_path: Optional[str] = None):
        if config_path and config_path != self._config_path_override:
            self._config_path_override = config_path
            self._config = None  # 재로드 강제
        if self._config is None:
            self._load_config()
    
    def _load_config(self) -> None:
        """설정 파일 로드"""
        config_path = self._get_config_path()
        
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f)
        else:
            # 기본 설정
            self._config = self._get_default_config()
    
    def _get_config_path(self) -> Path:
        """설정 파일 경로 반환"""
        # 생성자에서 넘긴 경로 우선
        if self._config_path_override:
            return Path(self._config_path_override)
        
        # 환경 변수로 오버라이드 가능
        env_path = os.getenv("SDP_CONFIG_PATH")
        if env_path:
            return Path(env_path)
        
        # 기본 경로: 프로젝트 루트/config/settings.yaml
        # src/config/config_loader.py → 프로젝트 루트
        project_root = Path(__file__).parent.parent.parent
        return project_root / "config" / "settings.yaml"
    
    def _get_default_config(self) -> Dict[str, Any]:
        """기본 설정 반환 (settings.yaml과 동기화)"""
        return {
            "llm": {
                "provider": "google",
                "model_name": "gemini-2.5-flash",
                "temperature": 0.7,
                "max_tokens": 65536,
            },
            "react_loop": {
                "max_steps": 5,
                "max_consecutive_failures": 3,
            },
            "agent": {
                "max_steps": 5,
                "max_reflection": 3,
                "enable_streaming": True,
            },
            "context": {
                "max_history": 20,
                "storage_dir": "data/context",
            },
            "lessons": {
                "storage_file": "data/lessons.json",
                "max_lessons": 100,
            },
            "paths": {
                "data_dir": "data",
                "resources_dir": "data/resources",
                "output_dir": "output_docs",
            },
            "resources": {
                "project": {
                    "statuses": ["active", "archived", "completed"],
                },
                "thread": {
                    "priorities": ["low", "medium", "high", "critical"],
                    "statuses": ["open", "in_progress", "resolved", "closed"],
                },
                "feed": {
                    "types": ["message", "update", "comment", "attachment", "status_change"],
                },
            },
            "tools": {
                "search": {
                    "max_results": 5,
                    "verify_ssl": False,
                },
                "file": {
                    "max_read_size": 10000,
                },
            },
            "output": {
                "verbose": True,
                "show_thought": True,
                "preview_length": 100,
            },
            "mcp_servers": [],
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        설정 값 조회 (dot notation 지원)
        
        예: config.get("llm.model_name")
        """
        keys = key.split(".")
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """설정 섹션 전체 반환"""
        return self._config.get(section, {})
    
    @property
    def llm(self) -> Dict[str, Any]:
        """LLM 설정"""
        return self.get_section("llm")
    
    @property
    def react_loop(self) -> Dict[str, Any]:
        """ReAct Loop 설정"""
        return self.get_section("react_loop")
    
    @property
    def memory(self) -> Dict[str, Any]:
        """Memory 설정"""
        return self.get_section("memory")
    
    @property
    def tools(self) -> Dict[str, Any]:
        """Tools 설정"""
        return self.get_section("tools")
    
    @property
    def output(self) -> Dict[str, Any]:
        """Output 설정"""
        return self.get_section("output")
    
    def reload(self) -> None:
        """설정 다시 로드"""
        self._config = None
        self._load_config()


# 싱글톤 인스턴스
config = ConfigLoader()
