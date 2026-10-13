"""LLM implementation backed by the `claude` CLI, not the API.

Why this exists: the direct `anthropic` SDK bills API credits. The `claude` CLI
authenticates against a Claude.ai subscription, so routing extraction through it uses
the owner's existing plan instead of metered credits. The extractor takes an injected
client (Protocol in extractor.py), so this is a second implementation, not a fork.

Trade-offs, stated because they are real:

- **No `output_config.format`.** The CLI has no strict-schema parameter, so the schema
  is requested in the prompt and enforced after the fact by `schema.validate`.
  Validation was already rejecting rather than clamping, which is what makes this
  safe: a malformed record fails loudly instead of being stored.
- **Subscription rate limits apply**, not credit balance. A long run can be throttled,
  so the caller should use `--limit` and expect to resume.
- **Slower per item** than the API: a process spawn plus CLI startup each call.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
from typing import Any

# Strip a ```json fence if one appears despite the instruction.
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)
# Last-resort recovery: the outermost {...} in the output.
_OBJECT = re.compile(r"\{.*\}", re.DOTALL)

DEFAULT_TIMEOUT = 180


class ClaudeCliNotAvailable(RuntimeError):
    pass


def available() -> bool:
    return shutil.which("claude") is not None


def _run_in_own_group(argv: list[str], prompt: str,
                      timeout: int) -> tuple[str, str, int | None]:
    """Run a command with a timeout that is actually enforceable.

    `subprocess.run(timeout=...)` kills only the direct child and then drains its
    pipes. The `claude` CLI is a Node wrapper that spawns its own processes, and
    those inherit the pipe write-ends: killing the wrapper leaves them holding the
    pipe open, so the drain blocks and the timeout never surfaces. Observed in an
    unattended run -- a call with a 180-second limit was still alive after 45
    minutes, and the stage above it never hit its own 20-minute limit either,
    because it was blocked in the same way.

    Running the child in its own session means one signal reaches the whole tree.

    Returns (stdout, stderr, returncode); a returncode of None means it timed out.
    """
    proc = subprocess.Popen(
        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
        start_new_session=True,          # its own process group, so killpg works
    )
    try:
        stdout, stderr = proc.communicate(prompt, timeout=timeout)
        return stdout, stderr, proc.returncode
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        try:
            # The tree is dead, so this returns promptly; the bound is belt and
            # braces against a process that ignores the signal.
            stdout, stderr = proc.communicate(timeout=10)
        except Exception:
            stdout, stderr = "", ""
        return stdout or "", stderr or "", None


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()


class ClaudeCliLLM:
    def __init__(self, timeout: int = DEFAULT_TIMEOUT, model: str | None = None):
        if not available():
            raise ClaudeCliNotAvailable(
                "`claude` is not on PATH. Install Node 18+, then: "
                "npm install -g @anthropic-ai/claude-code"
            )
        self._timeout = timeout
        self._model = model or os.environ.get("CLAUDE_CLI_MODEL", "claude-cli")

    @property
    def model(self) -> str:
        return self._model

    def extract(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build(system, user, schema)
        argv = ["claude", "-p"]
        if self._model and self._model != "claude-cli":
            argv += ["--model", self._model]
        stdout, stderr, code = _run_in_own_group(argv, prompt, self._timeout)
        if code is None:
            raise RuntimeError(f"claude CLI timed out after {self._timeout}s")
        if code != 0:
            raise RuntimeError(
                f"claude CLI exited {code}: "
                f"{(stderr or stdout or '').strip()[:200]}"
            )
        return parse_json(stdout)

    @staticmethod
    def _build(system: str, user: str, schema: dict[str, Any]) -> str:
        """One prompt, because `claude -p` has no separate system channel.

        The schema is inlined and the no-prose instruction is repeated at the end,
        where it is least likely to be lost in a long article.
        """
        return (
            f"{system}\n\n"
            "## OUTPUT CONTRACT\n"
            "Return ONLY a single JSON object matching this JSON Schema. No prose, no "
            "explanation, no markdown fence, nothing before or after the object.\n\n"
            f"{json.dumps(schema, indent=2)}\n\n"
            "---\n\n"
            f"{user}\n\n"
            "Return only the JSON object."
        )


def parse_json(raw: str) -> dict[str, Any]:
    """Recover the JSON object from CLI output.

    Tolerant of a stray fence or a leading sentence, because the cost of a retry is a
    whole model call. It is *not* tolerant of garbage: anything unparseable raises, so
    the pipeline records a failure rather than storing a guess.
    """
    text = (raw or "").strip()
    if not text:
        raise RuntimeError("claude CLI returned no output")
    candidate = _FENCE.sub("", text).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    match = _OBJECT.search(candidate)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"unparseable JSON from CLI: {exc}") from exc
    raise RuntimeError(f"no JSON object in CLI output: {candidate[:160]}")
