from collections.abc import Callable

import pytest

from agent_os.backends import (
    AuthStatus,
    BackendAdapter,
    BackendRegistry,
)
from agent_os.schemas import ArchitectBrief
from agent_os.state import SimonState


class FakeAdapter:
    name = "fake"
    binary_name = "fake-cli"
    supported_roles = frozenset({"architect", "executor"})

    def build_invoker(self, role: str) -> Callable[[SimonState], object]:
        return lambda state: state

    def authentication_status(self) -> AuthStatus:
        return AuthStatus(status="unknown", detail="test adapter")


class ArchitectOnlyAdapter:
    name = "architect-only"
    binary_name = "architect-cli"
    supported_roles = frozenset({"architect"})

    def build_invoker(self, role: str) -> Callable[[SimonState], object]:
        return lambda state: ArchitectBrief(files=[], changes=[], verify_cmd="")

    def authentication_status(self) -> AuthStatus:
        return AuthStatus(status="unknown")


def test_register_and_resolve_returns_same_adapter() -> None:
    registry = BackendRegistry()
    adapter = FakeAdapter()

    registry.register(adapter)

    assert registry.names == ("fake",)
    assert registry.resolve("architect", "fake") is adapter
    assert registry.resolve("executor", "fake") is adapter


def test_register_rejects_name_collision() -> None:
    registry = BackendRegistry()
    registry.register(FakeAdapter())

    with pytest.raises(ValueError, match="already registered: fake"):
        registry.register(FakeAdapter())


def test_resolve_unknown_name_lists_registered_adapters() -> None:
    registry = BackendRegistry()
    registry.register(FakeAdapter())

    with pytest.raises(ValueError, match="Unknown backend adapter 'missing'.*fake"):
        registry.resolve("architect", "missing")


def test_resolve_rejects_unsupported_role() -> None:
    registry = BackendRegistry()
    registry.register(ArchitectOnlyAdapter())

    with pytest.raises(ValueError, match="does not support role 'executor'"):
        registry.resolve("executor", "architect-only")


def test_protocol_shape_and_auth_status() -> None:
    adapter: BackendAdapter = FakeAdapter()
    assert adapter.binary_name == "fake-cli"
    assert adapter.supported_roles == frozenset({"architect", "executor"})
    assert adapter.authentication_status().status == "unknown"
