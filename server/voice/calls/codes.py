"""His 6-digit call code: the only key a guest needs to call him, with a limit on wrong guesses per client."""

import hmac
import re
import secrets
import time
from collections import deque

from voice.config import SPEAKERS
from voice.storage import read_json, speaker_dir, write_json

CODE_PATTERN = re.compile(r"\d{6}")
# Ten wrong codes from one client in ten minutes and that client is refused until the window passes.
MAX_WRONG_CODES = 10
WRONG_CODE_WINDOW_S = 600


class CodeRefused(Exception):
    """A guest's code was wrong or they guessed too often; the message can be shown as it is."""


class CallCodes:
    """Reads, creates and checks the speakers' call codes (stored as `call_code` in settings.json)."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.wrong: dict[str, deque[float]] = {}

    def code_for(self, speaker: str) -> str:
        """The speaker's call code, created the first time it is asked for."""
        return self.runtime.settings(speaker).get("call_code") or self.regenerate(speaker)

    def regenerate(self, speaker: str) -> str:
        """Gives the speaker a new code; the old link stops working at once."""
        taken = {self.runtime.settings(other).get("call_code") for other in SPEAKERS}
        code = f"{secrets.randbelow(1_000_000):06d}"
        while code in taken:
            code = f"{secrets.randbelow(1_000_000):06d}"
        path = speaker_dir(speaker) / "settings.json"
        write_json(path, {**read_json(path, {}), "call_code": code})
        self.runtime.commit_volumes()
        return code

    def speaker_for(self, code: str, client: str) -> str:
        """The speaker this code calls; raises CodeRefused for a wrong code or too many wrong tries."""
        recent = self._recent_wrong(client)
        if len(recent) >= MAX_WRONG_CODES:
            raise CodeRefused("Too many wrong call codes from this device. Wait ten minutes and try again.")
        for speaker in SPEAKERS:
            known = self.runtime.settings(speaker).get("call_code")
            if known and CODE_PATTERN.fullmatch(code) and hmac.compare_digest(known, code):
                return speaker
        recent.append(time.monotonic())
        self.wrong[client] = recent
        raise CodeRefused("That call code isn't right. Check the six digits and try again.")

    def _recent_wrong(self, client: str) -> deque[float]:
        """This client's wrong tries inside the window (older ones are forgotten)."""
        recent = self.wrong.pop(client, deque())
        while recent and time.monotonic() - recent[0] > WRONG_CODE_WINDOW_S:
            recent.popleft()
        if recent:
            # Only clients with recent wrong tries stay in the table, so it never grows without bound.
            self.wrong[client] = recent
        return recent
