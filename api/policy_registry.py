from __future__ import annotations

import importlib.util
import inspect
import re
from dataclasses import dataclass
from pathlib import Path
from shutil import move
from tempfile import NamedTemporaryFile
from typing import Callable, Literal

from des.network.routing import RoutingPolicy
from des.network.scheduling import SchedulingPolicy
from des.network.server_queue import ServerQueuePolicy

PolicyKind = Literal["server_router", "server_queue", "station_scheduler"]


@dataclass(frozen=True)
class RegisteredPolicy:
    id: str
    name: str
    kind: PolicyKind
    source_file: str
    description: str | None
    factory: Callable[[], object]


class PolicyRegistry:
    def __init__(self, storage_dir: Path) -> None:
        self._storage_dir = storage_dir
        self._policies: dict[str, RegisteredPolicy] = {}
        self._ensure_storage_dir()
        self.reload()

    def set_storage_dir(self, storage_dir: Path) -> None:
        self._storage_dir = storage_dir
        self._ensure_storage_dir()
        self.reload()

    def _ensure_storage_dir(self) -> None:
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def reload(self) -> None:
        policies: dict[str, RegisteredPolicy] = {}
        for path in sorted(self._storage_dir.glob("*.py")):
            for policy in self._load_policy_file(path):
                if policy.id in policies:
                    raise ValueError(f"Duplicate uploaded policy id '{policy.id}'")
                policies[policy.id] = policy
        self._policies = policies

    def upload(self, filename: str, content: bytes) -> list[RegisteredPolicy]:
        safe_name = _sanitize_filename(filename)
        if not safe_name.endswith(".py"):
            raise ValueError("Uploaded policy files must have a .py extension.")

        with NamedTemporaryFile("wb", suffix=".py", delete=False, dir=self._storage_dir) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            uploaded = self._load_policy_file(tmp_path, source_name=safe_name)
            if not uploaded:
                raise ValueError(
                    "No policies were found. Define ROUTERS, SERVER_QUEUE_POLICIES, "
                    "or STATION_SCHEDULERS in the uploaded module."
                )
            final_path = self._storage_dir / safe_name
            move(str(tmp_path), final_path)
            self.reload()
            return [policy for policy in self._policies.values() if policy.source_file == safe_name]
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def list_grouped(self) -> dict[str, list[dict[str, str | None]]]:
        grouped: dict[str, list[dict[str, str | None]]] = {
            "server_routing": [],
            "server_queue": [],
            "station_scheduling": [],
        }
        for policy in sorted(self._policies.values(), key=lambda item: (item.kind, item.name.lower(), item.id)):
            key = (
                "server_routing" if policy.kind == "server_router"
                else "server_queue" if policy.kind == "server_queue"
                else "station_scheduling"
            )
            grouped[key].append(
                {
                    "id": policy.id,
                    "name": policy.name,
                    "kind": policy.kind,
                    "source_file": policy.source_file,
                    "description": policy.description,
                }
            )
        return grouped

    def build_router(self, policy_id: str) -> RoutingPolicy:
        policy = self._require_policy(policy_id, "server_router")
        instance = policy.factory()
        if not isinstance(instance, RoutingPolicy):
            raise TypeError(f"Uploaded router '{policy_id}' did not produce a RoutingPolicy instance.")
        return instance

    def build_server_queue_policy(self, policy_id: str) -> ServerQueuePolicy:
        policy = self._require_policy(policy_id, "server_queue")
        instance = policy.factory()
        if not isinstance(instance, ServerQueuePolicy):
            raise TypeError(f"Uploaded server queue policy '{policy_id}' did not produce a ServerQueuePolicy instance.")
        return instance

    def build_station_scheduler(self, policy_id: str) -> SchedulingPolicy:
        policy = self._require_policy(policy_id, "station_scheduler")
        instance = policy.factory()
        if not isinstance(instance, SchedulingPolicy):
            raise TypeError(f"Uploaded station scheduler '{policy_id}' did not produce a SchedulingPolicy instance.")
        return instance

    def _require_policy(self, policy_id: str, kind: PolicyKind) -> RegisteredPolicy:
        try:
            policy = self._policies[policy_id]
        except KeyError as exc:
            raise ValueError(f"Unknown uploaded policy '{policy_id}'") from exc
        if policy.kind != kind:
            raise ValueError(
                f"Uploaded policy '{policy_id}' is a {policy.kind}, not a {kind}."
            )
        return policy

    def _load_policy_file(self, path: Path, source_name: str | None = None) -> list[RegisteredPolicy]:
        module_name = f"uploaded_policy_{path.stem}_{abs(hash(path.resolve()))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Unable to load policy file '{path.name}'")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        source_file = source_name or path.name
        descriptions = getattr(module, "POLICY_DESCRIPTIONS", {})
        policies: list[RegisteredPolicy] = []
        policies.extend(
            self._collect_kind(
                definitions=getattr(module, "ROUTERS", {}),
                kind="server_router",
                source_file=source_file,
                descriptions=descriptions,
            )
        )
        policies.extend(
            self._collect_kind(
                definitions=getattr(module, "SERVER_QUEUE_POLICIES", {}),
                kind="server_queue",
                source_file=source_file,
                descriptions=descriptions,
            )
        )
        policies.extend(
            self._collect_kind(
                definitions=getattr(module, "STATION_SCHEDULERS", {}),
                kind="station_scheduler",
                source_file=source_file,
                descriptions=descriptions,
            )
        )
        return policies

    def _collect_kind(
        self,
        *,
        definitions: object,
        kind: PolicyKind,
        source_file: str,
        descriptions: dict[str, str] | None = None,
    ) -> list[RegisteredPolicy]:
        normalized = _normalize_definitions(definitions)
        policies: list[RegisteredPolicy] = []
        for name, value in normalized:
            factory = _build_factory(value, kind, name)
            description = None
            if descriptions and name in descriptions:
                description = descriptions[name]
            elif inspect.getdoc(value):
                description = inspect.getdoc(value).splitlines()[0]
            policy_id = f"{Path(source_file).stem}:{kind}:{name}"
            policies.append(
                RegisteredPolicy(
                    id=policy_id,
                    name=name,
                    kind=kind,
                    source_file=source_file,
                    description=description,
                    factory=factory,
                )
            )
        return policies


def _normalize_definitions(definitions: object) -> list[tuple[str, object]]:
    if definitions is None:
        return []
    if isinstance(definitions, dict):
        return list(definitions.items())
    if isinstance(definitions, (list, tuple)):
        normalized: list[tuple[str, object]] = []
        for value in definitions:
            name = getattr(value, "__name__", None)
            if not name:
                raise ValueError("Uploaded policy lists must contain named callables or classes.")
            normalized.append((name, value))
        return normalized
    raise ValueError("Uploaded policy collections must be dicts, lists, or tuples.")


def _build_factory(value: object, kind: PolicyKind, name: str) -> Callable[[], object]:
    if inspect.isclass(value):
        cls = value

        def factory() -> object:
            return cls()

        _validate_instance(factory(), kind, name)
        return factory

    if callable(value):
        factory = value
        _validate_instance(factory(), kind, name)
        return factory

    raise ValueError(
        f"Uploaded policy '{name}' must be a zero-argument class or factory function."
    )


def _validate_instance(instance: object, kind: PolicyKind, name: str) -> None:
    expected = (
        RoutingPolicy if kind == "server_router"
        else ServerQueuePolicy if kind == "server_queue"
        else SchedulingPolicy
    )
    if not isinstance(instance, expected):
        raise ValueError(
            f"Uploaded policy '{name}' did not produce a {expected.__name__} instance."
        )


def _sanitize_filename(filename: str) -> str:
    name = Path(filename).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not cleaned:
        raise ValueError("Invalid upload filename.")
    return cleaned


registry = PolicyRegistry(Path(__file__).resolve().parent.parent / "uploaded_policies")
