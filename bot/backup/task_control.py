"""Pause/cancel control that persists immediately and interrupts waits."""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

CheckFn = Callable[[], Awaitable[bool]]


class ControlCommand(str, Enum):
    PAUSE = "pause"
    CANCEL = "cancel"
    STOP = "stop"


class WorkerPhase(str, Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    DRAINING = "draining"
    STOPPED = "stopped"
    PAUSED = "paused"


async def interruptible_sleep(
    seconds: float,
    should_stop: CheckFn,
    *,
    interval: float = 0.5,
) -> bool:
    """
    Sleep in small slices. Returns True if stopped early, False if full sleep elapsed.
    """
    remaining = max(0.0, float(seconds))
    while remaining > 0:
        if await should_stop():
            return True
        step = min(interval, remaining)
        await asyncio.sleep(step)
        remaining -= step
    return await should_stop()


async def interruptible_flood_wait(
    seconds: int,
    should_stop: CheckFn,
) -> bool:
    return await interruptible_sleep(seconds, should_stop, interval=1.0)


def control_status_line(control: Optional[str], phase: Optional[str]) -> str:
    if control == ControlCommand.PAUSE.value:
        if phase == WorkerPhase.DRAINING.value:
            return "⏸️ **Pause requested** — finishing current message, then stopping."
        return "⏸️ **Pause requested** — will stop when the current step completes."
    if control in (ControlCommand.CANCEL.value, ControlCommand.STOP.value):
        if phase == WorkerPhase.DRAINING.value:
            return "⏹️ **Cancel requested** — finishing in-flight work, then halting."
        return "⏹️ **Cancel requested** — halting as soon as the current step completes."
    if phase == WorkerPhase.PAUSED.value:
        return "⏸️ **Paused** — worker is idle."
    if phase == WorkerPhase.STOPPED.value:
        return "⏹️ **Stopped** — worker is idle."
    if phase == WorkerPhase.PROCESSING.value:
        return "⚡ **Working** on a message."
    return ""