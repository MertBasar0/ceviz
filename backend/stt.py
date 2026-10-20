from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("watch_ceviz.stt")

# whisper:<faster-whisper model name or Hugging Face repo>; never a path or an option.
_COMPARE_MODEL = re.compile(r"^whisper:[A-Za-z0-9][A-Za-z0-9._-]{0,63}(/[A-Za-z0-9][A-Za-z0-9._-]{0,99})?$")


@dataclass
class TranscriptionResult:
    transcript: str
    source: str
    error: str | None = None


class WatchSTT:
    def __init__(self) -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.environ.get("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe")
        self.language = os.environ.get("OPENAI_STT_LANGUAGE", "").strip()
        # STT motoru: auto (once lokal whisper, yoksa openai) | local | openai
        # | phone (bu makinede large-v3'e yer yok; iPhone cozer ve metni gonderir)
        self.engine = os.environ.get("WATCH_CEVIZ_STT_ENGINE", "auto").strip().lower() or "auto"

    @property
    def on_phone(self) -> bool:
        return self.engine == "phone"

    @property
    def compare_with_whisper(self) -> bool:
        return bool(self.compare_engines)

    @property
    def compare_engines(self) -> list[str]:
        """WATCH_CEVIZ_STT_COMPARE in phone mode: engines that also transcribe each capture, so
        their text sits beside the phone's on the job. The phone's text is the one used.

        `whisper` is the service's own Whisper model; `whisper:<model>` another faster-whisper
        model, for example `whisper:large-v3-turbo`. Comma-separated, in the order they run.
        """
        if not self.on_phone:
            return []
        engines: list[str] = []
        for item in os.environ.get("WATCH_CEVIZ_STT_COMPARE", "").split(","):
            item = item.strip()
            engine = "whisper" if item.lower() == "whisper" else item
            if (engine == "whisper" or _COMPARE_MODEL.match(engine)) and engine not in engines:
                engines.append(engine)
        return engines

    @staticmethod
    def speech_hints() -> list[str]:
        """Proper nouns the recognizer should expect: Whisper's hotwords, also sent to the iPhone."""
        try:
            import local_whisper
            words = local_whisper.hotwords() or ""
        except Exception:
            words = os.environ.get("WATCH_CEVIZ_WHISPER_HOTWORDS", "")
        return [word.strip()[:40] for word in words.split(",") if word.strip()][:50]

    def whisper_transcript(self, payload: dict[str, Any], engine: str = "whisper") -> dict[str, Any]:
        """The same capture through a comparison engine (see compare_engines). Never raises."""
        model = engine.split(":", 1)[1] if engine.startswith("whisper:") else None
        label = f"local-whisper:{model}" if model else "local-whisper"
        started = time.perf_counter()
        try:
            import local_whisper
            audio = base64.b64decode(payload.get("audio_data") or "", validate=True)
            language = self.language_from_payload(payload) or self.language or None
            if model:
                text, device = local_whisper.transcribe_bytes_with(model, audio, payload.get("format", "m4a"), language)
            else:
                text = local_whisper.transcribe_bytes(audio, payload.get("format", "m4a"), language)
                device = local_whisper.active_device()
            return {"engine": f"{label}:{device}", "transcript": (text or "").strip(),
                    "seconds": round(time.perf_counter() - started, 2)}
        except Exception as exc:
            logger.warning("Comparison %s failed: %s", label, exc)
            return {"engine": label, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}

    @staticmethod
    def language_from_payload(payload: dict[str, Any]) -> str | None:
        """Istemcinin gonderdigi locale'den ("en-US", "tr-TR") dil kodu cikar.
        Yoksa None → Whisper otomatik algilar."""
        locale = str(payload.get("locale") or "").strip()
        if not locale:
            return None
        code = locale.replace("_", "-").split("-")[0].lower()
        return code or None

    @classmethod
    def _error(cls, payload: dict[str, Any], english: str, turkish: str) -> str:
        return turkish if cls.language_from_payload(payload) == "tr" else english

    def transcribe_watch_payload(self, payload: dict[str, Any]) -> TranscriptionResult:
        provided_transcript = (payload.get("transcript") or "").strip()
        if provided_transcript:
            engine = str(payload.get("transcript_source") or "").strip()
            return TranscriptionResult(transcript=provided_transcript,
                                       source=f"iphone:{engine}" if engine else "client")

        if self.on_phone:
            reason = str(payload.get("transcript_error") or "").strip()
            return TranscriptionResult(
                transcript="", source="none",
                error=self._error(
                    payload,
                    "This computer leaves speech recognition to the iPhone, and no text arrived: "
                    + (reason or "update the Ceviz iPhone app"),
                    "Bu bilgisayarda konuşmayı iPhone çözüyor ama metin gelmedi: "
                    + (reason or "iPhone'daki Ceviz uygulamasını güncelle"),
                ),
            )

        audio_b64 = (payload.get("audio_data") or "").strip()
        if not audio_b64:
            return TranscriptionResult(
                transcript="", source="none",
                error=self._error(payload, "audio_data is empty", "audio_data boş"),
            )

        try:
            audio_bytes = base64.b64decode(audio_b64, validate=True)
        except Exception:
            return TranscriptionResult(
                transcript="", source="none",
                error=self._error(payload, "audio_data is not valid base64", "audio_data base64 olarak çözülemedi"),
            )

        if not audio_bytes:
            return TranscriptionResult(
                transcript="", source="none",
                error=self._error(payload, "decoded audio data is empty", "çözülen ses verisi boş"),
            )

        # 1) Lokal Whisper (key'siz, gizli) — engine auto/local
        local_error: Exception | None = None
        if self.engine in {"auto", "local"}:
            try:
                import local_whisper
            except Exception:
                local_whisper = None
            if local_whisper is not None and local_whisper.is_available():
                try:
                    text = (local_whisper.transcribe_bytes(
                        audio_bytes,
                        payload.get("format", "m4a"),
                        self.language_from_payload(payload) or self.language or None,
                    ) or "").strip()
                    if text:
                        return TranscriptionResult(transcript=text, source=f"local-whisper:{local_whisper.active_device()}")
                    if self.engine == "local":
                        return TranscriptionResult(
                            transcript="", source="none",
                            error=self._error(payload, "local Whisper returned an empty transcript", "local whisper boş metin döndürdü"),
                        )
                except Exception as exc:
                    # Logged in every mode: on 11 October this was swallowed, and every command only
                    # said "no transcript" while the real cause was a dead CUDA context.
                    logger.warning("Local Whisper failed: %s", exc)
                    if self.engine == "local":
                        prefix = self._error(payload, "local Whisper error", "local whisper hatası")
                        return TranscriptionResult(transcript="", source="none", error=f"{prefix}: {exc}")
                    local_error = exc  # auto: OpenAI'ye dus
            elif self.engine == "local":
                return TranscriptionResult(
                    transcript="", source="none",
                    error=self._error(payload, "faster-whisper is not installed", "faster-whisper kurulu değil"),
                )

        # 2) OpenAI fallback (engine auto/openai) — anahtar gerekir
        if not self.api_key and local_error is not None:
            return TranscriptionResult(
                transcript="", source="none",
                error=self._error(
                    payload,
                    f"Speech recognition is unavailable: local Whisper error: {local_error}; OPENAI_API_KEY is not set",
                    f"STT yok: lokal whisper hatası: {local_error}; OPENAI_API_KEY tanımlı değil",
                ),
            )
        if not self.api_key:
            return TranscriptionResult(
                transcript="", source="none",
                error=self._error(
                    payload,
                    "Speech recognition is unavailable: local Whisper produced no transcript and OPENAI_API_KEY is not set",
                    "STT yok: lokal whisper transkript üretemedi ve OPENAI_API_KEY tanımlı değil",
                ),
            )

        try:
            transcript = self._transcribe_with_openai(audio_bytes, payload.get("format", "m4a"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            return TranscriptionResult(transcript="", source="none", error=f"STT HTTP {exc.code}: {details}")
        except urllib.error.URLError as exc:
            prefix = self._error(payload, "STT network error", "STT ağ hatası")
            return TranscriptionResult(transcript="", source="none", error=f"{prefix}: {exc}")
        except Exception as exc:
            prefix = self._error(payload, "STT error", "STT hatası")
            return TranscriptionResult(transcript="", source="none", error=f"{prefix}: {exc}")

        transcript = transcript.strip()
        if not transcript:
            return TranscriptionResult(
                transcript="", source="none",
                error=self._error(payload, "STT returned an empty transcript", "STT boş metin döndürdü"),
            )

        return TranscriptionResult(transcript=transcript, source="openai")

    def _transcribe_with_openai(self, audio_bytes: bytes, audio_format: str) -> str:
        boundary = f"----WatchCevizBoundary{uuid.uuid4().hex}"
        filename = f"watch-command.{audio_format or 'm4a'}"
        content_type = self._guess_content_type(filename)

        body = bytearray()
        body.extend(self._field(boundary, "model", self.model))
        if self.language:
            body.extend(self._field(boundary, "language", self.language))
        body.extend(self._file(boundary, "file", filename, content_type, audio_bytes))
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        request = urllib.request.Request(
            url=f"{self.base_url}/audio/transcriptions",
            data=bytes(body),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))

        return str(payload.get("text") or "")

    def _field(self, boundary: str, name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode("utf-8")

    def _file(self, boundary: str, name: str, filename: str, content_type: str, data: bytes) -> bytes:
        head = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
        return head + data + b"\r\n"

    def _guess_content_type(self, filename: str) -> str:
        guessed, _ = mimetypes.guess_type(filename)
        return guessed or "application/octet-stream"
