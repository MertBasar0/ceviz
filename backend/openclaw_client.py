from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import logging

logger = logging.getLogger("watch_ceviz.openclaw_client")

try:
    from ceviz_pusula import CevizPusula
    _pusula_router: CevizPusula | None = None

    def _get_pusula() -> CevizPusula | None:
        global _pusula_router
        if _pusula_router is None:
            try:
                _pusula_router = CevizPusula()
            except Exception as exc:
                logger.warning(f"[pusula] Failed to initialize CevizPusula: {exc}")
                _pusula_router = None
        return _pusula_router
except Exception as e:
    logger.warning(f"[pusula] Could not import ceviz_pusula: {e}")
    _get_pusula = lambda: None

from job_outcome import normalize_job_outcome


@dataclass
class TaskResult:
    category: str
    canned_result: str
    watch_summary: str
    requires_phone_handoff: bool
    phone_report: str
    next_action: str | None
    outcome: str | None = None
    next_action_actor: str | None = None


class OpenClawUnavailable(RuntimeError):
    """`openclaw` calistirilabiliri bulunamadi — kurulum/PATH sorunu."""


@dataclass
class InvocationHandle:
    command: list[str]
    log_path: str
    started_at: float
    process: subprocess.Popen[Any]
    prompt: str


class OpenClawClient:
    """Thin OpenClaw CLI integration for watch-originated jobs."""

    REPORT_START = "<watch_ceviz_phone_report>"
    REPORT_END = "</watch_ceviz_phone_report>"
    META_START = "<watch_ceviz_meta>"
    META_END = "</watch_ceviz_meta>"

    def __init__(
        self,
        agent: str | None = None,
        runtime_dir: str | os.PathLike[str] | None = None,
        command_timeout_seconds: int | None = None,
    ) -> None:
        self.agent = agent or os.environ.get("OPENCLAW_WATCH_AGENT", "main")
        self.command_timeout_seconds = command_timeout_seconds or int(
            os.environ.get("OPENCLAW_WATCH_COMMAND_TIMEOUT_SECONDS", "3600")
        )
        self.runtime_dir = Path(
            runtime_dir
            or os.environ.get("OPENCLAW_WATCH_RUNTIME_DIR")
            or (Path(tempfile.gettempdir()) / "watch-ceviz-openclaw")
        )
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _assert_source_runtime_ready() -> None:
        """Reject commands while a source checkout has a partial dist build."""
        executable = shutil.which("openclaw")
        if not executable:
            return
        try:
            launcher = Path(executable).resolve()
            package_root = launcher.parent
            if not (package_root / ".git").exists():
                return
            runtime_entry = package_root / "dist" / "session-store.runtime.js"
            if not runtime_entry.exists():
                raise OpenClawUnavailable(
                    "OpenClaw is being rebuilt and is not ready yet. "
                    "Wait for the gateway to become ready, then resend the command."
                )
            probe = subprocess.run(  # noqa: S603
                ["node", "--input-type=module", "--eval", f'import({json.dumps(runtime_entry.as_uri())})'],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if probe.returncode != 0:
                raise OpenClawUnavailable(
                    "OpenClaw runtime files are incomplete during a rebuild. "
                    "Wait for the gateway to become ready, then resend the command."
                )
        except (OSError, subprocess.SubprocessError) as exc:
            raise OpenClawUnavailable(f"OpenClaw runtime preflight failed: {exc}") from exc

    def invoke_watch_command(self, payload: dict[str, Any]) -> InvocationHandle:
        self._assert_source_runtime_ready()
        prompt = self._build_prompt(payload)
        log_path = self.runtime_dir / f"watch-job-{uuid.uuid4().hex}.log"
        log_file = log_path.open("w", encoding="utf-8")
        command = [
            "openclaw",
            "agent",
            "--agent",
            self.agent,
            "--json",
            "--timeout",
            str(self.command_timeout_seconds),
            "--message",
            prompt,
        ]

        # cevizPusula: Semantic model routing
        user_transcript = (payload.get("transcript") or "").strip()
        pusula = _get_pusula()
        if pusula and user_transcript:
            try:
                continuation = (payload.get("_continuation_context") or "").strip()
                recent_job = self._get_recent_job_context()

                context_payload: dict[str, Any] = {}
                if continuation:
                    context_payload["continuation"] = continuation
                if recent_job:
                    context_payload["recent_job"] = recent_job
                    context_payload["last_tier_time"] = recent_job.get("created_at", 0)

                decision = pusula.route(user_transcript, context=context_payload)
                if decision.model:
                    command.extend(["--model", decision.model])
                if decision.thinking:
                    command.extend(["--thinking", decision.thinking])

                flags = []
                if decision.escalated:
                    flags.append("ESCALATED")
                if decision.hysteresis_applied:
                    flags.append("HYSTERESIS")
                if decision.context_used:
                    flags.append("CONTEXT")
                flags_str = f" [{', '.join(flags)}]" if flags else ""

                logger.info(
                    f"[pusula] '{user_transcript[:40]}' -> {decision.group}{flags_str} | "
                    f"model: {decision.model} (thinking: {decision.thinking}) | "
                    f"calls: {decision.jev_calls} | {decision.latency_ms}ms"
                )
            except Exception as pusula_err:
                logger.warning(f"[pusula] Routing error, proceeding with agent defaults: {pusula_err}")

        try:
            process = subprocess.Popen(  # noqa: S603
                command,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError as exc:
            log_file.close()
            raise OpenClawUnavailable(
                "OpenClaw CLI was not found on PATH. The Ceviz backend must run "
                "on the machine where OpenClaw is installed, and the service PATH "
                "must include the OpenClaw executable."
            ) from exc
        log_file.close()
        return InvocationHandle(
            command=command,
            log_path=str(log_path),
            started_at=time.time(),
            process=process,
            prompt=prompt,
        )

    def extract_result(self, log_path: str, locale: str = "") -> TaskResult:
        raw_output = Path(log_path).read_text(encoding="utf-8")
        parsed = json.loads(raw_output)
        payloads = parsed.get("result", {}).get("payloads", [])
        response_text = "\n\n".join(
            payload.get("text", "").strip()
            for payload in payloads
            if payload.get("text")
        ).strip()
        if not response_text:
            response_text = (
                "OpenClaw çağrısı tamamlandı ama metin yanıtı dönmedi."
                if self._locale_code(locale) == "tr"
                else "OpenClaw completed the command but returned no text response."
            )

        structured = self._extract_structured_payload(response_text)
        clean_text = structured["phone_report"] or response_text

        return TaskResult(
            category=structured["category"] or self._categorize_text(clean_text, locale),
            canned_result=clean_text,
            watch_summary=structured["watch_summary"] or self._build_watch_summary(clean_text, locale=locale),
            requires_phone_handoff=(
                structured["requires_phone_handoff"]
                if structured["requires_phone_handoff"] is not None
                else self._requires_phone_handoff(clean_text)
            ),
            phone_report=self._build_phone_report(clean_text, locale),
            next_action=structured["next_action"] or self._extract_next_action(clean_text),
            outcome=normalize_job_outcome("completed", structured.get("outcome")),
            next_action_actor=structured.get("next_action_actor"),
        )

    # --- Canli durum enjeksiyonu ---------------------------------------
    # Saat komutlari kendi session'inda calisiyor (agent:<id>:main), TUI /
    # webchat isleri baska session'da. Bu yuzden ajan "ne uzerinde
    # calisiyorsun?" sorusuna kendi transkriptinden bakip "is yok" diyor,
    # zorlandiginda hafizadan eski isleri anlatiyordu. Cozum: session
    # indeksinden CANLI durumu okuyup prompt'a gercek veri olarak vermek.

    @staticmethod
    def _get_recent_job_context(max_age_seconds: float = 900.0) -> dict[str, Any] | None:
        """Son 15 dakika icindeki son isi pusula baglami icin ceker."""
        try:
            jobs_path = Path.home() / ".openclaw" / "ceviz-state" / "jobs.json"
            if not jobs_path.is_file():
                return None
            data = json.loads(jobs_path.read_text(encoding="utf-8"))
            jobs = data.get("jobs", [])
            if not jobs:
                return None

            now = time.time()
            for job in reversed(jobs):
                created_at = job.get("created_at") or 0
                if not isinstance(created_at, (int, float)):
                    continue
                if (now - created_at) > max_age_seconds:
                    break
                status = job.get("status")
                if status in ("completed", "failed"):
                    model_used = None
                    inv = job.get("invocation") or {}
                    cmd = inv.get("command") or []
                    for idx, arg in enumerate(cmd):
                        if arg == "--model" and idx + 1 < len(cmd):
                            model_used = cmd[idx + 1]
                            break
                    return {
                        "transcript": job.get("transcript") or job.get("name") or "",
                        "watch_summary": job.get("watch_summary") or "",
                        "canned_result": job.get("canned_result") or "",
                        "created_at": created_at,
                        "model": model_used,
                        "status": status,
                    }
        except Exception:
            pass
        return None

    @staticmethod
    def _last_user_message(session_path: Path, max_tail: int = 200_000) -> str:
        """Buyuk transkriptleri bastan okumamak icin yalnizca kuyrugu tara."""
        try:
            size = session_path.stat().st_size
            with session_path.open("rb") as fh:
                if size > max_tail:
                    fh.seek(size - max_tail)
                    fh.readline()  # yarim satiri at
                raw = fh.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

        latest = ""
        for line in raw.splitlines():
            try:
                obj = json.loads(line)
            except Exception:
                continue
            message = obj.get("message") if isinstance(obj.get("message"), dict) else obj
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = message.get("content")
            if isinstance(content, list):
                content = " ".join(
                    str(part.get("text", "")) for part in content if isinstance(part, dict)
                )
            text = " ".join(str(content or "").split())
            if text:
                latest = text
        return latest

    def collect_live_status(self, limit: int = 4, window_hours: float = 24.0) -> list[str]:
        own_key = f"agent:{self.agent}:main"
        try:
            index_path = Path.home() / ".openclaw" / "agents" / self.agent / "sessions" / "sessions.json"
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        now_ms = time.time() * 1000
        rows: list[tuple[float, str, dict]] = []
        for key, info in (data.items() if isinstance(data, dict) else []):
            if not isinstance(info, dict):
                continue
            updated = info.get("updatedAt") or info.get("lastActivity") or 0
            if not isinstance(updated, (int, float)) or updated <= 0:
                continue
            if (now_ms - updated) > window_hours * 3600 * 1000:
                continue
            rows.append((updated, key, info))

        rows.sort(reverse=True)
        sessions_dir = Path.home() / ".openclaw" / "agents" / self.agent / "sessions"
        lines: list[str] = []
        for updated, key, info in rows[:limit]:
            minutes = max(0, int((now_ms - updated) / 60000))
            when = f"{minutes} dk önce" if minutes < 60 else f"{minutes // 60} sa önce"
            origin = info.get("origin") if isinstance(info.get("origin"), dict) else {}
            surface = str(origin.get("surface") or origin.get("provider") or "bilinmeyen")
            if key == own_key:
                surface += " (bu saat kanalı)"

            summary = ""
            session_id = info.get("sessionId")
            if session_id:
                summary = self._last_user_message(sessions_dir / f"{session_id}.jsonl")
            # Saat komutlari uzun prompt sarmalayicisi; kisalt.
            if summary.startswith("Bu istek Apple Watch"):
                summary = "(saatten gelen sesli komut)"
            if len(summary) > 160:
                summary = summary[:159].rstrip() + "…"

            lines.append(f"- {surface} · {when}: {summary or '(içerik okunamadı)'}")

        return lines

    def collect_background_activity(self, started_at: float, log_path: str, locale: str = "") -> list[str]:
        """Is sirasinda arkada ne oldu: kullanilan araclar + alt ajanlar.

        Rapora "ALT AJANLAR & ARACLAR" bolumu olarak girer. Veri iki
        kaynaktan: sonuc JSON'undaki toolSummary ve `openclaw sessions`
        listesindeki, is penceresi icinde guncellenmis subagent session'lari.
        """
        lines: list[str] = []

        try:
            parsed = json.loads(Path(log_path).read_text(encoding="utf-8"))
            summary = parsed.get("result", {}).get("meta", {}).get("toolSummary") or {}
            tools = summary.get("tools") or []
            if tools:
                calls = summary.get("calls", 0)
                failures = summary.get("failures", 0)
                if self._locale_code(locale) == "tr":
                    fail_note = f", {failures} hata" if failures else ""
                    lines.append(f"Araçlar: {', '.join(tools)} ({calls} çağrı{fail_note})")
                else:
                    fail_note = f", {failures} failed" if failures else ""
                    lines.append(f"Tools: {', '.join(tools)} ({calls} calls{fail_note})")
        except Exception:
            pass

        # `openclaw sessions` CLI'i spawn edilen oturumlari listelemiyor;
        # dogrudan agent'in sessions.json indeksinden oku. Is penceresinde
        # guncellenen, ana oturum ve kanal oturumlari disindaki her oturum
        # arka plan calismasi sayilir.
        try:
            index_path = Path.home() / ".openclaw" / "agents" / self.agent / "sessions" / "sessions.json"
            data = json.loads(index_path.read_text(encoding="utf-8"))
            window_start_ms = (started_at - 5) * 1000
            channel_markers = (
                ":whatsapp:", ":telegram:", ":discord:", ":slack:", ":matrix:",
                ":qqbot:", ":signal:", ":imessage:", ":sms:",
            )
            for key, info in (data.items() if isinstance(data, dict) else []):
                if not isinstance(info, dict):
                    continue
                if key == f"agent:{self.agent}:main" or any(m in key for m in channel_markers):
                    continue
                updated = info.get("updatedAt") or info.get("lastActivity") or 0
                if not isinstance(updated, (int, float)) or updated < window_start_ms:
                    continue
                title = info.get("displayName") or info.get("title") or info.get("label") or key.split(":")[-1]
                prefix = "Alt ajan/oturum" if self._locale_code(locale) == "tr" else "Subagent/session"
                lines.append(f"{prefix}: {str(title)[:90]}")
        except Exception:
            pass

        return lines

    def parse_failure(
        self,
        log_path: str,
        return_code: int = 1,
        locale: str = "",
        parse_error: str | None = None,
    ) -> tuple[str, str]:
        """Başarısız OpenClaw çağrısından kullanıcı dostu (watch_summary, phone_report) üretir.

        Prompt metnini veya dahili sistem loglarını kullanıcı ekranına sızdırmaz.
        JSON içindeki gerçek hata mesajını (503 Overloaded, Rate Limit, Timeout vb.)
        çıkarıp anlaşılır mesajlar üretir.
        """
        is_tr = self._locale_code(locale) == "tr"
        error_msg = ""
        is_timeout = False

        p = Path(log_path)
        if p.exists():
            try:
                raw_output = p.read_text(encoding="utf-8", errors="replace")
                data = json.loads(raw_output)
                if isinstance(data, dict):
                    if data.get("status") == "timeout" or data.get("stopReason") == "timeout":
                        is_timeout = True

                    # 1. meta.error
                    meta_err = data.get("result", {}).get("meta", {}).get("error")
                    if isinstance(meta_err, dict):
                        error_msg = meta_err.get("message") or meta_err.get("kind") or ""

                    # 2. direct error
                    if not error_msg:
                        dir_err = data.get("error")
                        if isinstance(dir_err, dict):
                            error_msg = dir_err.get("message") or dir_err.get("kind") or ""
                        elif isinstance(dir_err, str):
                            error_msg = dir_err

                    # 3. payloads text if error
                    if not error_msg and data.get("status") == "error":
                        payloads = data.get("result", {}).get("payloads", [])
                        for pay in payloads:
                            if isinstance(pay, dict) and pay.get("text"):
                                error_msg = pay["text"].strip()
                                break
            except Exception:
                pass

        if is_timeout:
            if is_tr:
                summary = "İstek zaman aşımına uğradı."
                detail = "OpenClaw çağrısı zaman aşımına uğradı (model belirlenen süre içinde yanıt vermedi). Lütfen tekrar deneyin."
            else:
                summary = "Request timed out."
                detail = "The OpenClaw call timed out waiting for the model. Please try again."
            return summary, detail

        err_lower = (error_msg or "").lower()
        if "overloaded" in err_lower or "503" in err_lower:
            if is_tr:
                summary = "Model servisi aşırı yüklendi (503). Lütfen az sonra tekrar deneyin."
                detail = (
                    "Yapay zekâ servisi (NVIDIA NIM) şu anda aşırı yoğunluk nedeniyle yanıt veremedi "
                    "(503 Service Temporarily Overloaded).\n\n"
                    "Bu durum sağlayıcı kaynaklı geçici bir yoğunluktur. Lütfen birkaç saniye bekleyip komutunuzu tekrar iletin."
                )
            else:
                summary = "AI service is overloaded (503). Please retry shortly."
                detail = (
                    "The upstream AI provider reported high load (503 Service Temporarily Overloaded).\n\n"
                    "This is a temporary provider issue. Please wait a few moments and try again."
                )
            return summary, detail

        if "rate limit" in err_lower or "429" in err_lower:
            if is_tr:
                summary = "İstek limiti aşıldı (429). Lütfen biraz bekleyin."
                detail = "Yapay zekâ servisi istek sınırına ulaştı (Rate Limit 429). Lütfen kısa bir süre bekleyip tekrar deneyin."
            else:
                summary = "Rate limit reached (429). Please wait."
                detail = "The AI service reached its rate limit (429). Please wait a moment and try again."
            return summary, detail

        if error_msg:
            clean_msg = error_msg.strip()
            if is_tr:
                summary = f"Model hatası: {clean_msg[:120]}"
                detail = f"Model çağrısı sırasında bir hata oluştu:\n\n{clean_msg}"
            else:
                summary = f"Model error: {clean_msg[:120]}"
                detail = f"An error occurred during the model call:\n\n{clean_msg}"
            return summary, detail

        if parse_error:
            if is_tr:
                summary = "Model yanıtı çözümlenemedi."
                detail = f"OpenClaw yanıtı işlenirken bir ayrıştırma hatası oluştu:\n{parse_error}"
            else:
                summary = "Failed to parse model response."
                detail = f"An error occurred while parsing the OpenClaw response:\n{parse_error}"
            return summary, detail

        if is_tr:
            summary = f"İşlem tamamlanamadı (kod: {return_code})."
            detail = (
                f"OpenClaw işlemi {return_code} koduyla sonlandı ve görev sonucu doğrulanamadı.\n"
                "Model yanıt üretememiş veya bağlantı kesilmiş olabilir. Lütfen komutunuzu tekrar deneyin."
            )
        else:
            summary = f"Operation failed (code: {return_code})."
            detail = (
                f"The OpenClaw call exited with code {return_code} and could not produce a confirmed result.\n"
                "Please try again."
            )
        return summary, detail

    def read_log_tail(self, log_path: str, max_chars: int = 1200) -> str:
        if not Path(log_path).exists():
            return ""
        contents = Path(log_path).read_text(encoding="utf-8", errors="replace")
        return contents[-max_chars:].strip()

    # Cihaz dili -> (dil adi, hedef dilde vurgulu direktif). Prompt iskeleti
    # Turkce kalir (tum davranis kurallari orada test edildi) ama CIKTI dili
    # kullanicinin cihaz diline gore belirlenir.
    LANGUAGE_DIRECTIVES = {
        "tr": ("Türkçe", "Tüm çıktıyı Türkçe üret."),
        "en": ("English", "IMPORTANT: Write every part of your answer in English."),
        "de": ("Deutsch", "WICHTIG: Antworte vollständig auf Deutsch."),
        "fr": ("Français", "IMPORTANT : rédige toute ta réponse en français."),
        "es": ("Español", "IMPORTANTE: escribe toda tu respuesta en español."),
        "it": ("Italiano", "IMPORTANTE: scrivi tutta la risposta in italiano."),
        "nl": ("Nederlands", "BELANGRIJK: schrijf je volledige antwoord in het Nederlands."),
        "pt": ("Português", "IMPORTANTE: escreva toda a resposta em português."),
    }

    @staticmethod
    def _locale_code(locale: str) -> str:
        return str(locale or "").strip().replace("_", "-").split("-")[0].lower() or "en"

    def _language_block(self, payload: dict[str, Any]) -> str:
        locale = str(payload.get("locale") or "").strip()
        code = self._locale_code(locale)
        name, emphatic = self.LANGUAGE_DIRECTIVES.get(
            code, (locale or code, f"IMPORTANT: Write your entire answer in the user's language ({locale or code}).")
        )
        return (
            f"ÇIKTI DİLİ: {name} (kullanıcının cihaz dili). Rapor bloğu, watch_summary, "
            f"next_action ve tüm serbest metinler bu dilde olmalı; alan adları/JSON anahtarları değişmez.\n"
            f"{emphatic}\n"
        )

    def _build_prompt(self, payload: dict[str, Any]) -> str:
        audio_format = payload.get("format", "unknown")
        client_timestamp = payload.get("client_timestamp", "unknown")
        audio_size = len(payload.get("audio_data", ""))
        optional_transcript = (payload.get("transcript") or "").strip()
        stt_source = (payload.get("_stt_source") or "unknown").strip()
        stt_error = (payload.get("_stt_error") or "").strip()

        transcript_line = (
            f"Çözümlenen transkript: {optional_transcript}\n"
            if optional_transcript
            else "Transkript üretilemedi.\n"
        )
        continuation = (payload.get("_continuation_context") or "").strip()
        continuation_block = f"\n{continuation}\n" if continuation else ""

        # Saat kendi session'inda calisir; makinede olan biteni gormesi icin
        # canli durumu prompt'a gercek veri olarak koy.
        try:
            live = self.collect_live_status()
        except Exception:
            live = []
        live_block = ""
        if live:
            live_block = (
                "\nCANLI DURUM (bu makinedeki oturumların son etkinliği — gerçek veri, "
                "senin transkriptinde görünmese de geçerli):\n"
                + "\n".join(live)
                + "\nBu listeyi 'ne üzerinde çalışıyorsun / aktif işler neler' türü sorularda "
                "BİRİNCİL kaynak olarak kullan. Kendi konuşma geçmişinde iş görmüyorsan 'iş yok' "
                "deme; buradaki oturumlara bak. Hafızadaki/eski notlardaki işleri güncel işmiş "
                "gibi sunma — yalnızca burada listelenenler güncel.\n"
            )
        stt_status_line = f"STT kaynağı: {stt_source}\n"
        stt_error_line = f"STT fallback nedeni: {stt_error}\n" if stt_error else ""

        return (
            "Bu istek Apple Watch kaynaklı Watch Ceviz backend entegrasyonundan geliyor. "
            "Amaç, saatten gelen kısa komutları telefona devredilebilir net bir sonuca çevirmek.\n\n"
            f"Ses formatı: {audio_format}\n"
            f"İstemci zaman damgası: {client_timestamp}\n"
            f"Base64 ses yükü uzunluğu: {audio_size}\n"
            f"{stt_status_line}"
            f"{stt_error_line}"
            f"{transcript_line}"
            f"{continuation_block}"
            f"{live_block}\n"
            f"{self._language_block(payload)}"
            "Eğer gerçek transkript yoksa bunu açıkça söyle ve en güvenli bir sonraki adımı öner. "
            "Transkript bozuk/anlamsız görünüyorsa TAHMİNLE İŞLEM YAPMA: ne anladığını tek cümleyle söyle, "
            "requires_phone_handoff=true yap ve next_action olarak düzeltilmiş komutu onaylatmayı öner. "
            "watch_summary HER ZAMAN somut olsun: tam olarak ne yapıldığını veya neden yapılmadığını söyle; "
            "'önceki rapora işlendi' gibi bağlama atıf yapan opak ifadeler kullanma. "
            "Yanıtı iki blok halinde üret ve marker metinlerini aynen koru.\n"
            f"1) İlk blok tam olarak {self.REPORT_START} ile başlayıp {self.REPORT_END} ile bitsin. "
            "Bu blokta telefonda gösterilecek raporu yukarıdaki ÇIKTI DİLİ talimatına göre yaz. Raporda şu sırayı kullan: "
            "1. Kısa durum, 2. Ne anlaşıldı / sınırlama, 3. Önerilen sonraki adım.\n"
            f"2) İkinci blok tam olarak {self.META_START} ile başlayıp {self.META_END} ile bitsin. "
            "Bu blokta tek satır geçerli JSON nesnesi ver. Şema: "
            '{"watch_summary":"...","next_action":"..."|null,"next_action_actor":"agent"|"user","outcome":"done"|"blocked"|"needs_input","requires_phone_handoff":true,"category":"..."}. '
            "outcome: istenen iş gerçekten yapıldıysa done, yapılamadıysa blocked, kullanıcıdan bilgi/onay gerekiyorsa needs_input. "
            "next_action_actor: next_action'ı AJAN kendisi çalıştırabilecekse agent yaz ve next_action'ı komut kipinde üret; "
            "yalnızca kullanıcının davranışı gerekiyorsa user yaz (bu tür öneriler kullanıcıya bilgi olarak gösterilir, ajana geri gönderilmez). "
            "user türü next_action'da 'onaylayın/onayla' gibi seçim-bekleyen ifadeler KULLANMA — ortada onaylanacak bir şey yok; "
            "bunun yerine kullanıcının ne söylemesi gerektiğini çıktı dilinde açık bir yönerge olarak yaz "
            "(TR: 'Yeni komut verin: ...', EN: 'Say this instead: ...'). "
            "Yapılacak bir sonraki adım YOKSA next_action'ı null bırak ve next_action_actor'ı da null yap. "
            "'Yok.', 'Ek işlem gerekmiyor.', 'İşlem gerekmiyor.' gibi dolgu cümlelerini next_action olarak ASLA yazma — "
            "bunlar buton haline gelip tekrar sana gönderiliyor ve kısır döngü yaratıyor; durumu anlatmak istiyorsan rapor bloğunda anlat. "
            "watch_summary tek cümle ve 160 karakter altında olsun. next_action net, uygulanabilir tek adım olsun. "
            "JSON dışında meta bloğunda başka açıklama yazma."
        )

    def _extract_structured_payload(self, text: str) -> dict[str, Any]:
        phone_report = self._extract_tagged_block(text, self.REPORT_START, self.REPORT_END)
        meta_raw = self._extract_tagged_block(text, self.META_START, self.META_END)
        meta: dict[str, Any] = {}

        if meta_raw:
            try:
                parsed_meta = json.loads(meta_raw)
                if isinstance(parsed_meta, dict):
                    meta = parsed_meta
            except json.JSONDecodeError:
                meta = {}

        return {
            "phone_report": (phone_report or self._strip_structured_blocks(text)).strip(),
            "watch_summary": self._clean_optional_text(meta.get("watch_summary")),
            "next_action": self._clean_optional_text(meta.get("next_action")),
            "category": self._clean_optional_text(meta.get("category")),
            "requires_phone_handoff": self._coerce_optional_bool(meta.get("requires_phone_handoff")),
            "outcome": self._clean_optional_text(meta.get("outcome")),
            "next_action_actor": self._clean_optional_text(meta.get("next_action_actor")),
        }

    def _extract_tagged_block(self, text: str, start_tag: str, end_tag: str) -> str | None:
        pattern = re.escape(start_tag) + r"\s*(.*?)\s*" + re.escape(end_tag)
        match = re.search(pattern, text, flags=re.DOTALL)
        if not match:
            return None
        block = match.group(1).strip()
        return block or None

    def _strip_structured_blocks(self, text: str) -> str:
        stripped = re.sub(
            re.escape(self.REPORT_START) + r".*?" + re.escape(self.REPORT_END),
            "",
            text,
            flags=re.DOTALL,
        )
        stripped = re.sub(
            re.escape(self.META_START) + r".*?" + re.escape(self.META_END),
            "",
            stripped,
            flags=re.DOTALL,
        )
        return stripped.strip()

    def _clean_optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if text.lower() == "null":
            return None
        return text or None

    def _coerce_optional_bool(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "1", "evet"}:
                return True
            if normalized in {"false", "no", "0", "hayır", "hayir"}:
                return False
        return None

    def _categorize_text(self, text: str, locale: str = "") -> str:
        text_lower = text.lower()
        english = self._locale_code(locale) != "tr"
        if any(word in text_lower for word in ["mail", "e-posta", "posta"]):
            return "Email" if english else "E-posta İşlemleri"
        if any(word in text_lower for word in ["takvim", "calendar", "meeting", "toplantı"]):
            return "Calendar / Schedule" if english else "Takvim / Program"
        if any(word in text_lower for word in ["kod", "git", "pull request", "pr", "review"]):
            return "Software / Code" if english else "Yazılım / Kod"
        return "OpenClaw Assistant" if english else "OpenClaw Asistan"

    def _build_watch_summary(self, text: str, max_len: int = 200, locale: str = "") -> str:
        normalized = " ".join(part.strip() for part in text.splitlines() if part.strip())
        normalized = re.sub(r"\b[123]\s*[\.)]\s*", "", normalized).strip()
        if not normalized:
            return (
                "Sonuç üretildi ama özet metni boş döndü."
                if self._locale_code(locale) == "tr"
                else "The result was produced, but its summary was empty."
            )

        preferred_chunks = []
        for separator in [". ", "\n", "; "]:
            preferred_chunks.extend(chunk.strip() for chunk in normalized.split(separator) if chunk.strip())
        preferred_chunks.append(normalized)

        for chunk in preferred_chunks:
            if len(chunk) < 8:
                continue
            if len(chunk) <= max_len:
                return chunk

        return normalized[: max_len - 1].rstrip() + "…"

    def _requires_phone_handoff(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return True

        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        text_lower = stripped.lower()
        code_markers = ["```", "def ", "class ", "diff ", "+++", "---", "{" , "}"]
        has_code_like_content = any(marker in stripped for marker in code_markers)
        has_list_like_content = sum(line.startswith(("-", "*", "•")) for line in lines) >= 3
        has_many_lines = len(lines) >= 5
        is_long = len(stripped) > 280
        has_dense_guidance = any(keyword in text_lower for keyword in ["adım", "next", "sonraki adım", "checklist", "liste"]) and len(stripped) > 180
        return has_code_like_content or has_list_like_content or has_many_lines or is_long or has_dense_guidance

    def _build_phone_report(self, text: str, locale: str = "") -> str:
        return text.strip() or (
            "OpenClaw çağrısı tamamlandı ama ayrıntılı rapor boş döndü."
            if self._locale_code(locale) == "tr"
            else "OpenClaw completed the command, but the detailed report was empty."
        )

    def _extract_next_action(self, text: str) -> str | None:
        stripped = text.strip()
        if not stripped:
            return None

        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        heading_markers = [
            "3. önerilen sonraki adım",
            "3) önerilen sonraki adım",
            "önerilen sonraki adım:",
            "sonraki adım:",
            "suggested next action:",
            "next action:",
        ]

        for index, line in enumerate(lines):
            normalized = line.lower()
            if normalized in heading_markers:
                collected: list[str] = []
                for candidate in lines[index + 1 :]:
                    candidate_lower = candidate.lower()
                    if any(
                        candidate_lower.startswith(prefix)
                        for prefix in ["1.", "2.", "3.", "1)", "2)", "3)"]
                    ):
                        break
                    collected.append(candidate.lstrip("-• ").strip())
                result = " ".join(part for part in collected if part).strip()
                if result:
                    return result

            for marker in heading_markers:
                if normalized.startswith(marker):
                    inline = line[len(marker):].lstrip(" :-").strip()
                    if inline:
                        return inline

        return None
