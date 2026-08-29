"""Asynchronous streaming client and process manager for Antigravity (agy) CLI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from agy_bot.config import config
from agy_bot.session_manager import UserSession

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """Base event representing a stream update from agy CLI."""
    event_type: str
    conversation_id: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InitEvent(StreamEvent):
    tools: List[str] = field(default_factory=list)
    cwd: str = ""


@dataclass
class StepUpdateEvent(StreamEvent):
    step_index: int = 0
    state: str = "ACTIVE"  # ACTIVE | DONE
    step_type: str = ""   # tool | agent_response | user_input | system_message
    tool_name: Optional[str] = None
    tool_info: Dict[str, Any] = field(default_factory=dict)
    text_delta: str = ""
    thinking_delta: str = ""
    duration_seconds: float = 0.0
    usage: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResultEvent(StreamEvent):
    status: str = "SUCCESS"  # SUCCESS | ERROR
    response: str = ""
    duration_seconds: float = 0.0
    num_turns: int = 1
    usage: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None


class AgyClient:
    """Manages spawning, streaming, and terminating agy CLI subcommands."""

    def __init__(self, agy_bin: Optional[str] = None):
        self.agy_bin = agy_bin or config.agy_bin

    def build_command_args(self, prompt: str, session: UserSession) -> List[str]:
        """Construct CLI argument list for the given prompt and user session."""
        args = [
            self.agy_bin,
            "-p", prompt,
            "--output-format", "stream-json",
        ]

        if session.active_conversation_id:
            args.extend(["--conversation", session.active_conversation_id])

        if session.model:
            args.extend(["--model", session.model])

        if session.effort:
            args.extend(["--effort", session.effort])

        if session.mode:
            args.extend(["--mode", session.mode])

        if session.auto_approve:
            args.append("--dangerously-skip-permissions")

        return args

    async def execute_stream(
        self,
        prompt: str,
        session: UserSession,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Execute agy CLI asynchronously and yield parsed streaming events.
        Handles process tracking on the user session and clean cancellation.
        """
        cmd = self.build_command_args(prompt, session)
        cwd = session.working_dir

        if not os.path.exists(cwd):
            cwd = config.default_working_dir

        logger.info("Spawning agy command: %s (cwd: %s)", " ".join(cmd), cwd)

        proc: Optional[asyncio.subprocess.Process] = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            session.current_process = proc

            accumulated_response: List[str] = []
            final_result_seen = False

            while True:
                if proc.stdout is None:
                    break
                line_bytes = await proc.stdout.readline()
                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    event_name = data.get("event")

                    if event_name == "init":
                        init_payload = data.get("init", {})
                        conv_id = data.get("conversation_id")
                        if conv_id:
                            session.active_conversation_id = conv_id
                        yield InitEvent(
                            event_type="init",
                            conversation_id=conv_id,
                            tools=init_payload.get("tools", []),
                            cwd=init_payload.get("cwd", cwd),
                            raw_data=data,
                        )

                    elif event_name == "step_update":
                        su = data.get("step_update", {})
                        conv_id = su.get("conversation_id")
                        if conv_id and not session.active_conversation_id:
                            session.active_conversation_id = conv_id

                        text_delta = su.get("text_delta", "")
                        if text_delta:
                            accumulated_response.append(text_delta)

                        yield StepUpdateEvent(
                            event_type="step_update",
                            conversation_id=conv_id,
                            step_index=su.get("step_index", 0),
                            state=su.get("state", "ACTIVE"),
                            step_type=su.get("step_type", ""),
                            tool_name=su.get("tool_name"),
                            tool_info=su.get("tool_info", {}),
                            text_delta=text_delta,
                            duration_seconds=su.get("duration_seconds", 0.0),
                            usage=su.get("usage", {}),
                            raw_data=data,
                        )

                    elif event_name == "result":
                        final_result_seen = True
                        res = data.get("result", {})
                        conv_id = res.get("conversation_id")
                        if conv_id:
                            session.active_conversation_id = conv_id

                        resp_text = res.get("response", "".join(accumulated_response))
                        yield ResultEvent(
                            event_type="result",
                            conversation_id=conv_id,
                            status=res.get("status", "SUCCESS"),
                            response=resp_text,
                            duration_seconds=res.get("duration_seconds", 0.0),
                            num_turns=res.get("num_turns", 1),
                            usage=res.get("usage", {}),
                            raw_data=data,
                        )

                except json.JSONDecodeError:
                    # Non-JSON output or plain log line
                    logger.debug("Received non-JSON output from agy: %s", line)

            # Wait for process exit
            stdout_rem, stderr_bytes = await proc.communicate()
            if proc.returncode != 0 and not final_result_seen:
                stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
                yield ResultEvent(
                    event_type="result",
                    conversation_id=session.active_conversation_id,
                    status="ERROR",
                    response="",
                    error_message=stderr_text or f"agy process exited with returncode {proc.returncode}",
                )

        except asyncio.CancelledError:
            logger.info("Execution cancelled by user. Terminating agy process...")
            if proc is not None:
                await self._kill_process_safely(proc)
            raise

        except Exception as exc:
            logger.exception("Unexpected error executing agy CLI: %s", exc)
            yield ResultEvent(
                event_type="result",
                conversation_id=session.active_conversation_id,
                status="ERROR",
                response="",
                error_message=str(exc),
            )

        finally:
            session.current_process = None

    async def _kill_process_safely(self, proc: asyncio.subprocess.Process) -> None:
        """Gracefully interrupt or kill a running subprocess."""
        try:
            if proc.returncode is not None:
                return
            proc.send_signal(signal.SIGINT)
            try:
                await asyncio.wait_for(proc.wait(), timeout=1.5)
            except asyncio.TimeoutError:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.warning("Error killing agy process: %s", e)


# Global client instance
agy_client = AgyClient()
