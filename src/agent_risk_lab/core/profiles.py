from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SEP = "\n--- shared defense fragment ---\n"


def normalize(text: str) -> str:
    text = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.splitlines()).rstrip("\n") + "\n"


def compose_effective_prompt(base_instruction: str, profile_prompt: str) -> str:
    """Return the base unchanged when the compiled profile has no content."""
    if not profile_prompt.strip():
        return base_instruction
    return f"{base_instruction.rstrip()}\n\n{profile_prompt.strip()}"


@dataclass(frozen=True)
class ResolvedProfile:
    name: str
    version: int
    description: str
    change_summary: str
    fragment_names: tuple[str, ...]
    compiled_profile_prompt: str
    compiled_profile_sha256: str
    profile_path: Path
    requested_version: int | None
    resolved_version: int

    # Compatibility aliases for callers and schema 2.0 logs.
    @property
    def id(self) -> str:
        return self.name

    @property
    def fragment_ids(self) -> tuple[str, ...]:
        return self.fragment_names

    @property
    def text(self) -> str:
        return self.compiled_profile_prompt

    @property
    def sha256(self) -> str:
        # This hashes only the compiled shared-profile addition, not metadata.
        return self.compiled_profile_sha256


class ProfileLoader:
    def __init__(self, root: Path) -> None:
        self.root = root

    @staticmethod
    def _toml(path: Path, kind: str) -> dict[str, Any]:
        try:
            return tomllib.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ValueError(f"missing {kind}: {path}") from error
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
            raise ValueError(f"invalid {kind}: {path}") from error

    def _registry(self) -> dict[str, tuple[int, tuple[int, ...]]]:
        path = self.root / "registry.toml"
        data = self._toml(path, "profile registry TOML")
        if data.get("schema_version") != 1:
            raise ValueError(f"unsupported profile registry schema_version in {path}")
        raw_profiles = data.get("profiles")
        if not isinstance(raw_profiles, dict):
            raise ValueError(f"profile registry has no profiles table: {path}")
        profiles: dict[str, tuple[int, tuple[int, ...]]] = {}
        for name, raw in raw_profiles.items():
            if not isinstance(name, str) or not isinstance(raw, dict):
                raise ValueError(f"invalid profile registry entry in {path}: {name!r}")
            latest = raw.get("latest")
            published_raw = raw.get("published")
            if not isinstance(latest, int) or isinstance(latest, bool) or latest <= 0:
                raise ValueError(f"profile {name!r} latest must be a positive integer in {path}")
            if not isinstance(published_raw, list) or any(
                not isinstance(item, int) or isinstance(item, bool) or item <= 0
                for item in published_raw
            ):
                raise ValueError(f"profile {name!r} published must be positive integers in {path}")
            published = tuple(published_raw)
            if len(set(published)) != len(published):
                raise ValueError(f"profile {name!r} has duplicate published versions in {path}")
            if latest not in published:
                raise ValueError(f"profile {name!r} latest v{latest} is not published in {path}")
            for version in published:
                profile_path = self.root / name / f"v{version}" / "profile.toml"
                if not profile_path.is_file() or profile_path.is_symlink():
                    raise ValueError(
                        f"profile {name!r} published v{version} is missing: {profile_path}"
                    )
            profiles[name] = (latest, published)
        return profiles

    def list_profiles(self) -> list[str]:
        return sorted(self._registry())

    def _fragment_path(self, version_root: Path, fragment: str, profile_name: str, version: int) -> Path:
        relative = Path(fragment)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"profile {profile_name!r} v{version} has unsafe fragment path: {fragment!r}")
        candidate = version_root / relative
        if candidate.is_symlink():
            raise ValueError(f"profile {profile_name!r} v{version} fragment is a symlink: {fragment!r}")
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as error:
            raise ValueError(
                f"profile {profile_name!r} v{version} fragment does not exist: {fragment!r}"
            ) from error
        root = version_root.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError(f"profile {profile_name!r} v{version} has unsafe fragment: {fragment!r}")
        return resolved

    def load_profile(self, profile_name: str, version: int | None = None) -> ResolvedProfile:
        registry = self._registry()
        if profile_name not in registry:
            raise ValueError(f"unknown profile {profile_name!r} in {self.root / 'registry.toml'}")
        if version is not None and (
            not isinstance(version, int) or isinstance(version, bool) or version <= 0
        ):
            raise ValueError(f"profile {profile_name!r} requested version must be a positive integer")
        latest, published = registry[profile_name]
        resolved_version = latest if version is None else version
        if resolved_version not in published:
            raise ValueError(
                f"profile {profile_name!r} requested v{resolved_version} is not published"
            )
        version_root = self.root / profile_name / f"v{resolved_version}"
        profile_path = version_root / "profile.toml"
        raw = self._toml(profile_path, "profile TOML")
        if raw.get("name") != profile_name:
            raise ValueError(f"profile name mismatch for {profile_path}: expected {profile_name!r}")
        if raw.get("version") != resolved_version:
            raise ValueError(
                f"profile version mismatch for {profile_path}: expected {resolved_version}"
            )
        if raw.get("status") != "published":
            raise ValueError(f"profile {profile_name!r} v{resolved_version} is not published: {profile_path}")
        fragments = raw.get("fragments")
        if not isinstance(fragments, list) or any(not isinstance(item, str) for item in fragments):
            raise ValueError(f"profile fragments must be a string list: {profile_path}")
        description = raw.get("description")
        change_summary = raw.get("change_summary")
        if not isinstance(description, str) or not isinstance(change_summary, str):
            raise ValueError(f"profile metadata must be strings: {profile_path}")
        parts = [
            normalize(
                self._fragment_path(version_root, fragment, profile_name, resolved_version).read_text(
                    encoding="utf-8"
                )
            ).rstrip("\n")
            for fragment in fragments
        ]
        compiled = (SEP.join(parts) + "\n") if parts else ""
        return ResolvedProfile(
            name=profile_name,
            version=resolved_version,
            description=description.strip(),
            change_summary=change_summary.strip(),
            fragment_names=tuple(fragments),
            compiled_profile_prompt=compiled,
            compiled_profile_sha256=hashlib.sha256(compiled.encode()).hexdigest(),
            profile_path=profile_path,
            requested_version=version,
            resolved_version=resolved_version,
        )

    def render_profile(self, profile_name: str, version: int | None = None) -> str:
        return self.load_profile(profile_name, version).compiled_profile_prompt

    def render_system_instruction(
        self, base_system: str, profile_name: str, version: int | None = None
    ) -> str:
        profile = self.load_profile(profile_name, version)
        return compose_effective_prompt(normalize(base_system), profile.compiled_profile_prompt)
