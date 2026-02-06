"""
Input Controller
Karn Core — Stable Input Layer
Compatible with Global Interrupt & Action Executor
"""

from loguru import logger
from typing import Optional

from core.control.global_interrupt import GLOBAL_INTERRUPT


class InputController:
    def __init__(self):
        self._executing = False
        self._last_input: Optional[str] = None

    # =================================================
    # INPUT READ
    # =================================================
    def read(self) -> Optional[str]:
        """
        Blocking input reader.
        Returns cleaned input or None if interrupted.
        """

        # 🔴 If interrupt already active, do not read
        if GLOBAL_INTERRUPT.is_triggered():
            logger.debug("Input read aborted (global interrupt active)")
            return None

        try:
            self._executing = True
            raw = input("Karn > ").strip()
            self._last_input = raw

            # 🔴 Interrupt detected mid-input
            if GLOBAL_INTERRUPT.is_triggered():
                logger.debug("Input interrupted during read")
                return None

            if not raw:
                return None

            return raw

        except KeyboardInterrupt:
            logger.warning("KeyboardInterrupt received during input")
            GLOBAL_INTERRUPT.trigger()
            return None

        except EOFError:
            logger.warning("EOF received — shutting down input")
            GLOBAL_INTERRUPT.trigger()
            return None

        finally:
            self._executing = False

    # =================================================
    # EXECUTION STATE
    # =================================================
    def reset_execution_state(self):
        """
        Called after interrupt or cancelled execution.
        """
        logger.debug("Resetting input execution state")
        self._executing = False
        self._last_input = None

    # =================================================
    # STATE HELPERS
    # =================================================
    def is_executing(self) -> bool:
        return self._executing

    def last_input(self) -> Optional[str]:
        return self._last_input
