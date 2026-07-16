from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .hashing import sha256_bytes


_CONFIG_ID = re.compile(r"[a-z0-9][a-z0-9_]*\Z")


@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    adapter_id: str
    api_key_env: str


@dataclass(frozen=True)
class TargetConfig:
    target_id: str
    provider_id: str
    adapter_id: str
    model: str
    network_permission_env: str
    sha256: str


class TargetLoader:
    def __init__(self, providers_dir: Path, targets_dir: Path) -> None:
        self.providers_dir = providers_dir
        self.targets_dir = targets_dir

    @staticmethod
    def _path(directory: Path, config_id: str) -> Path:
        if not _CONFIG_ID.fullmatch(config_id):
            raise ValueError("invalid configuration id")
        path = directory / f"{config_id}.toml"
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"unregistered configuration: {config_id}")
        return path

    @staticmethod
    def _required_text(data: dict[str, object], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"empty or missing {key}")
        return value

    def load_provider(self, provider_id: str) -> ProviderConfig:
        data = tomllib.loads(self._path(self.providers_dir, provider_id).read_text(encoding="utf-8"))
        configured_id = self._required_text(data, "provider_id")
        if configured_id != provider_id:
            raise ValueError("provider_id does not match provider filename")
        return ProviderConfig(
            provider_id=configured_id,
            adapter_id=self._required_text(data, "adapter_id"),
            api_key_env=self._required_text(data, "api_key_env"),
        )

    def load_target(self, target_id: str) -> tuple[TargetConfig, ProviderConfig]:
        path = self._path(self.targets_dir, target_id)
        raw = path.read_bytes()
        try:
            data = tomllib.loads(raw.decode("utf-8"))
        except UnicodeDecodeError as error:
            raise ValueError("target configuration must be UTF-8") from error
        configured_id = self._required_text(data, "target_id")
        if configured_id != target_id:
            raise ValueError("target_id does not match target filename")
        target = TargetConfig(
            target_id=configured_id,
            provider_id=self._required_text(data, "provider_id"),
            adapter_id=self._required_text(data, "adapter_id"),
            model=self._required_text(data, "model"),
            network_permission_env=self._required_text(data, "network_permission_env"),
            sha256=sha256_bytes(raw),
        )
        provider = self.load_provider(target.provider_id)
        if target.adapter_id != provider.adapter_id:
            raise ValueError("target adapter_id does not match provider")
        return target, provider

    def list_targets(self) -> list[str]:
        return sorted(path.stem for path in self.targets_dir.glob("*.toml") if path.is_file() and not path.is_symlink())
