"""Recovery command validation and application helpers."""

from __future__ import annotations

from typing import Optional

from environment.protocol import CommandKind, CommandResult, RecoveryCommand


def validate_command(cmd: RecoveryCommand) -> Optional[CommandResult]:
    if cmd.kind == CommandKind.SET_FAN_SPEED:
        try:
            speed = float(cmd.value)
        except (TypeError, ValueError):
            return CommandResult(success=False, message=f"fan_speed must be numeric, got: {cmd.value!r}")
        if not 0.0 <= speed <= 1.0:
            return CommandResult(success=False, message=f"fan_speed out of range: {speed}")
    elif cmd.kind == CommandKind.ENABLE_BYPASS:
        if not isinstance(cmd.value, bool):
            return CommandResult(success=False, message="enable_bypass requires bool value")
    elif cmd.kind == CommandKind.REDUCE_LOAD:
        if not isinstance(cmd.value, bool):
            return CommandResult(success=False, message="reduce_load requires bool value")
    else:
        return CommandResult(success=False, message=f"unknown command kind: {cmd.kind}")
    return None


def apply_command_to_state(
    cmd: RecoveryCommand,
    fan_speed: float,
    bypass_enabled: bool,
    load_reduced: bool,
) -> tuple[float, bool, bool, str]:
    if cmd.kind == CommandKind.SET_FAN_SPEED:
        return float(cmd.value), bypass_enabled, load_reduced, f"fan_speed set to {cmd.value}"
    if cmd.kind == CommandKind.ENABLE_BYPASS:
        return fan_speed, bool(cmd.value), load_reduced, f"bypass {'enabled' if cmd.value else 'disabled'}"
    if cmd.kind == CommandKind.REDUCE_LOAD:
        return fan_speed, bypass_enabled, bool(cmd.value), f"load {'reduced' if cmd.value else 'restored'}"
    raise ValueError(f"unsupported command: {cmd.kind}")
