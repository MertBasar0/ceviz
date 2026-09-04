import hashlib
import hmac
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
import time
from urllib.parse import parse_qs, urlparse
import uuid

logging.basicConfig(level=logging.INFO)

# Bos birakilirsa auth kapali (gelistirme kolayligi). Uretimde systemd
# unit'i WATCH_CEVIZ_AUTH_TOKEN ile calistirir; tum /api/* istekleri
# "Authorization: Bearer <token>" ister.
AUTH_TOKEN = os.environ.get("WATCH_CEVIZ_AUTH_TOKEN", "").strip()

CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"

# Dynamic job store for real OpenClaw processes
jobs_db = {}

# Is gecmisi diske yazilir: servis yeniden baslayinca (guc kesintisi,
# makine reboot'u, deploy) gecmis ve konusma zinciri kaybolmasin.
STATE_DIR = Path(os.environ.get("WATCH_CEVIZ_STATE_DIR", str(Path.home() / ".openclaw" / "ceviz-state")))
JOBS_STATE_PATH = STATE_DIR / "jobs.json"
MAX_PERSISTED_JOBS = 50

from openclaw_client import OpenClawClient, OpenClawUnavailable, TaskResult
from job_outcome import normalize_job_outcome
from push_notifier import PushNotifier
from stt import WatchSTT

openclaw_client = OpenClawClient()
stt_client = WatchSTT()
push_notifier = PushNotifier()


USER_COPY = {
    "en": {
        "command_received": "Command received: {transcript}. Processing.",
        "transcript_received": "Transcript received: {transcript}. Processing.",
        "speech_unclear": "Audio received, but the command was unclear. Details and a retry suggestion are available on iPhone.",
        "audio_processing": "Audio received. Processing the command.",
        "job_running": "{name} is processing.",
        "job_running_elapsed": "{summary} ({seconds}s)",
        "command_unclear": "Command unclear: {error}",
        "job_failed": "The job could not be completed. Details are available on iPhone.",
        "result_ready": "Result ready.",
        "handoff_needs_clarification": "The command is unclear. Details and a retry option are available on iPhone.",
        "handoff_failure_diagnosis": "The issue needs more detail. Logs and the next step are available on iPhone.",
        "handoff_approval_required": "Approval is required. Continue safely on iPhone.",
        "handoff_too_many_actions": "There are several actions to choose from. Continue on iPhone.",
        "handoff_low_confidence": "Confidence is low. Details and guidance are available on iPhone.",
        "handoff_logs_and_code": "This result contains code or logs. Open it on iPhone to review.",
        "handoff_action_required": "Continue on iPhone to approve or choose the next action.",
        "handoff_long_detail": "The result is detailed. It is easier to review on iPhone.",
        "handoff_job_missing": "The job was not found. Try again on iPhone.",
        "handoff_default": "The details are clearer on iPhone.",
        "default_task": "Task",
        "default_category": "OpenClaw Assistant",
        "running_analysis": "This job is currently running on OpenClaw. Elapsed: {seconds} seconds. Tap Refresh for the latest status.",
        "running_next": "Wait briefly and refresh this screen, then review the updated report on iPhone.",
        "failed_analysis": "The job could not be completed and no details are available.",
        "failed_next": "Review the error details, then retry from your Watch or send a clearer command.",
        "completed_analysis": "No result data is available.",
        "completed_next_with_summary": "Use the Watch summary for the quick result and continue from the detailed analysis below if needed.",
        "completed_next": "Continue from the detailed result below.",
        "section_category": "Category",
        "section_watch_summary": "Watch summary",
        "section_analysis": "Expanded analysis",
        "section_next": "Suggested next action",
        "section_activity": "Subagents & tools",
        "activity_eyebrow": "AGENTS",
        "backend_restart_report": "Ceviz restarted before it could recover the result. The OpenClaw job may still have run. Check its state before sending the command again.",
        "backend_restart_summary": "Ceviz restarted; the job's result is unconfirmed. Check before retrying.",
        "result_unconfirmed": "The result could not be confirmed. Check on iPhone before retrying.",
        "check_before_retry": "Check the job in OpenClaw before sending it again to avoid repeating an action.",
        "openclaw_started": "OpenClaw started processing the command.",
        "openclaw_started_no_transcript": "OpenClaw started, but no transcript was produced. The iPhone report will show the error and a retry suggestion.",
        "openclaw_waiting": "OpenClaw started processing; waiting for the result.",
        "command_name": "Command",
        "install_category": "Setup",
        "unknown_category": "Unknown",
        "detail_missing": "No details were found.",
        "task_missing": "Job not found.",
        "job_cancelled": "Ceviz stopped tracking this call. Cancellation in OpenClaw is not confirmed; check the job before sending it again.",
        "shortcut_missing": "Command text is empty. Send dictated or typed text to the backend from the Shortcut.",
    },
    "tr": {
        "command_received": "Komut alındı: {transcript}. İşleniyor.",
        "transcript_received": "Transkript alındı: {transcript}. İşleniyor.",
        "speech_unclear": "Ses alındı ama komut netleşmedi. Telefonda ayrıntı ve yeniden deneme önerisi var.",
        "audio_processing": "Ses alındı. Komut işleniyor.",
        "job_running": "{name} işleniyor.",
        "job_running_elapsed": "{summary} ({seconds} sn)",
        "command_unclear": "Komut netleşmedi: {error}",
        "job_failed": "Görev tamamlanamadı. Telefonda ayrıntı var.",
        "result_ready": "Sonuç hazır.",
        "handoff_needs_clarification": "Komut net değil. Telefonda ayrıntı ve yeniden deneme var.",
        "handoff_failure_diagnosis": "Sorun ayrıntılı görünüyor. Loglar ve sonraki adım telefonda.",
        "handoff_approval_required": "Onay gerekiyor. Telefonda devam etmek daha güvenli.",
        "handoff_too_many_actions": "Birden fazla aksiyon var. Telefonda seçim yapmak daha güvenli.",
        "handoff_low_confidence": "Yanıt güveni düşük. Telefonda ayrıntı ve yönlendirme var.",
        "handoff_logs_and_code": "Kod veya log var. Telefonda açıp inceleyelim.",
        "handoff_action_required": "Devam etmek için telefonda onay veya seçim gerekiyor.",
        "handoff_long_detail": "Detay uzun. Telefonda daha rahat inceleyebilirsin.",
        "handoff_job_missing": "Görev bulunamadı. Telefonda tekrar deneyebilirsin.",
        "handoff_default": "Detay telefonda daha net.",
        "default_task": "Görev",
        "default_category": "OpenClaw Asistan",
        "running_analysis": "Görev şu anda OpenClaw üzerinde işleniyor. Geçen süre: {seconds} saniye. Yenile ile güncel durumu çekebilirsin.",
        "running_next": "Biraz bekleyip bu ekranı yenile, ardından güncellenen raporu telefonda incele.",
        "failed_analysis": "Görev tamamlanamadı, ayrıntı bulunamadı.",
        "failed_next": "Hata detayını kontrol et, sonra saatten yeniden dene veya komutu daha net söyleyip tekrar gönder.",
        "completed_analysis": "Sonuç verisi bulunamadı.",
        "completed_next_with_summary": "Saat özetini hızlı sonuç olarak kullan, gerekiyorsa aşağıdaki ayrıntılı analize göre telefonda devam et.",
        "completed_next": "Aşağıdaki ayrıntılı sonuca göre telefonda devam et.",
        "section_category": "Kategori",
        "section_watch_summary": "Saat özeti",
        "section_analysis": "Ayrıntılı analiz",
        "section_next": "Önerilen sonraki adım",
        "section_activity": "Alt ajanlar & araçlar",
        "activity_eyebrow": "AJANLAR",
        "backend_restart_report": "Ceviz yeniden başlatıldığı için sonuç alınamadı. OpenClaw işi çalıştırmış olabilir. Komutu tekrar göndermeden önce durumunu kontrol et.",
        "backend_restart_summary": "Ceviz yeniden başlatıldı; sonuç doğrulanamadı. Yeniden denemeden önce kontrol et.",
        "result_unconfirmed": "Sonuç doğrulanamadı. Yeniden denemeden önce iPhone'da kontrol et.",
        "check_before_retry": "Aynı işlemi tekrarlamamak için komutu yeniden göndermeden önce OpenClaw'da işin durumunu kontrol et.",
        "openclaw_started": "OpenClaw çağrısı başlatıldı.",
        "openclaw_started_no_transcript": "OpenClaw çağrısı başlatıldı ancak transkript üretilemedi. Telefonda hata notu ve yeniden deneme önerisi gösterilecek.",
        "openclaw_waiting": "OpenClaw çağrısı başlatıldı, sonuç bekleniyor.",
        "command_name": "Komut",
        "install_category": "Kurulum",
        "unknown_category": "Bilinmeyen",
        "detail_missing": "Detay bulunamadı.",
        "task_missing": "Görev bulunamadı.",
        "job_cancelled": "Ceviz bu çağrıyı takip etmeyi durdurdu. OpenClaw'da iptal edildiği doğrulanamadı; komutu tekrar göndermeden önce kontrol et.",
        "shortcut_missing": "Komut metni boş. Kısayolda dikte veya metin alanını backend'e gönder.",
    },
}


def locale_code(value: dict | str | None) -> str:
    locale = value.get("locale") if isinstance(value, dict) else value
    code = str(locale or "").strip().replace("_", "-").split("-")[0].lower()
    return code if code in USER_COPY else "en"


def user_copy(value: dict | str | None, key: str, **values) -> str:
    return USER_COPY[locale_code(value)][key].format(**values)


def load_contract(name: str) -> dict:
    with (CONTRACTS_DIR / name).open("r") as f:
        return json.load(f)


def _schema_pointer(schema: dict, ref: str) -> dict:
    if not ref.startswith("#/"):
        raise ValueError(f"Unsupported schema ref: {ref}")

    node: dict | list = schema
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"Schema ref not found: {ref}")
        node = node[part]

    if not isinstance(node, dict):
        raise ValueError(f"Schema ref does not resolve to an object schema: {ref}")
    return node


def _matches_type(value, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "null":
        return value is None
    return True


def _validate_against_schema(value, schema_node: dict, root_schema: dict, path: str) -> list[str]:
    errors: list[str] = []

    if "$ref" in schema_node:
        return _validate_against_schema(value, _schema_pointer(root_schema, schema_node["$ref"]), root_schema, path)

    if "allOf" in schema_node:
        for part in schema_node["allOf"]:
            errors.extend(_validate_against_schema(value, part, root_schema, path))
        return errors

    expected_type = schema_node.get("type")
    if isinstance(expected_type, list):
        if not any(_matches_type(value, type_name) for type_name in expected_type):
            errors.append(f"Invalid type for {path}, expected one of {expected_type}")
            return errors
    elif isinstance(expected_type, str) and not _matches_type(value, expected_type):
        errors.append(f"Invalid type for {path}, expected {expected_type}")
        return errors

    if "enum" in schema_node and value not in schema_node["enum"]:
        errors.append(f"Invalid enum value for {path}: {value}")

    if isinstance(value, dict):
        properties = schema_node.get("properties", {})
        required = schema_node.get("required", [])

        for req in required:
            if req not in value:
                errors.append(f"Missing required field: {path}.{req}" if path else f"Missing required field: {req}")

        if schema_node.get("additionalProperties") is False:
            for prop in value:
                if prop not in properties:
                    errors.append(f"Unexpected field: {path}.{prop}" if path else f"Unexpected field: {prop}")

        for prop, prop_schema in properties.items():
            if prop in value:
                child_path = f"{path}.{prop}" if path else prop
                errors.extend(_validate_against_schema(value[prop], prop_schema, root_schema, child_path))

    if isinstance(value, list) and "items" in schema_node:
        item_schema = schema_node["items"]
        for index, item in enumerate(value):
            errors.extend(_validate_against_schema(item, item_schema, root_schema, f"{path}[{index}]"))

    return errors


def validate_payload(payload: dict, schema: dict) -> list[str]:
    return _validate_against_schema(payload, schema, schema, "")


def trim_watch_text(text: str, max_len: int = 200) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1].rstrip() + "…"


PHONE_HANDOFF_DETAIL_THRESHOLD = 140
PHONE_HANDOFF_ACTION_LIMIT = 3
LOW_CONFIDENCE_THRESHOLD = 0.55
CODE_OR_LOG_MARKERS = (
    "```",
    "traceback",
    "exception",
    "stack trace",
    "diff --git",
    "stderr",
    "stdout",
    "error:",
    "warn:",
    "info:",
    "log:",
    "logs:",
    "[error]",
    "[warn]",
    "[info]",
)
APPROVAL_MARKERS = (
    "onay",
    "approve",
    "approval",
    "izin gerekiyor",
    "requires approval",
)


def clean_text(value: str | None) -> str:
    return (value or "").strip()


def has_code_or_logs(text: str) -> bool:
    lowered = clean_text(text).lower()
    if not lowered:
        return False

    if any(marker in lowered for marker in CODE_OR_LOG_MARKERS):
        return True

    return any(token in lowered for token in (".py:", ".ts:", ".cs:", "line ", "stack", "terminal"))


def get_explicit_next_actions(job: dict) -> list[dict[str, str | None]]:
    raw_actions = job.get("next_actions")
    if not isinstance(raw_actions, list):
        return []

    normalized: list[dict[str, str | None]] = []
    for index, action in enumerate(raw_actions, start=1):
        if not isinstance(action, dict):
            continue

        label = clean_text(action.get("label") or action.get("title") or action.get("id") or f"Action {index}")
        kind = clean_text(action.get("kind") or "hint")
        action_id = clean_text(action.get("id") or f"action-{index}")
        target = clean_text(action.get("target")) or None

        normalized.append({
            "id": action_id,
            "label": trim_watch_text(label, max_len=80),
            "kind": kind,
            "target": target,
        })

    return normalized


def requires_phone_approval(job: dict) -> bool:
    if bool(job.get("requires_approval")) or bool(job.get("approval_required")):
        return True

    text_fragments = [
        clean_text(job.get("next_action")),
        clean_text(job.get("phone_report")),
        clean_text(job.get("canned_result")),
    ]
    text_fragments.extend(
        filter(
            None,
            [
                clean_text(action.get("label"))
                for action in get_explicit_next_actions(job)
            ],
        )
    )
    combined = " ".join(text_fragments).lower()
    return any(marker in combined for marker in APPROVAL_MARKERS)


def classify_handoff_reason(job: dict) -> str | None:
    status = clean_text(job.get("status")).lower()
    transcript = clean_text(job.get("transcript"))
    detail = clean_text(job.get("phone_report") or job.get("canned_result"))
    watch_summary = clean_text(job.get("watch_summary"))
    stt_error = clean_text(job.get("stt_error"))
    explicit_requires_handoff = job.get("requires_phone_handoff")
    explicit_actions = get_explicit_next_actions(job)
    confidence = job.get("confidence")
    low_confidence = bool(job.get("low_confidence"))

    outcome = normalize_job_outcome(status, job.get("outcome"))
    if status == "missing":
        return "job_missing"
    if status == "failed" or outcome == "blocked":
        return "failure_diagnosis"

    if outcome == "needs_input":
        return "needs_clarification"

    if stt_error or (status in {"running", "processing"} and not transcript):
        return "needs_clarification"

    if requires_phone_approval(job):
        return "approval_required"

    if len(explicit_actions) > PHONE_HANDOFF_ACTION_LIMIT:
        return "too_many_actions"

    if low_confidence:
        return "low_confidence"

    if isinstance(confidence, (int, float)) and confidence < LOW_CONFIDENCE_THRESHOLD:
        return "low_confidence"

    if has_code_or_logs(detail):
        return "logs_and_code"

    if len(detail) > PHONE_HANDOFF_DETAIL_THRESHOLD or len(watch_summary) > 200:
        return "long_detail"

    if explicit_requires_handoff is True and clean_text(job.get("next_action")):
        return "action_required"

    if explicit_requires_handoff is True:
        return "phone_review"

    return None


def build_processing_summary(
    stt_source: str,
    transcript: str,
    stt_error: str | None = None,
    locale: str = "",
) -> str:
    transcript = (transcript or "").strip()
    stt_error = (stt_error or "").strip()

    if transcript:
        transcript_preview = trim_watch_text(f'"{transcript}"', max_len=96)
        if stt_source == "openai":
            return trim_watch_text(user_copy(locale, "command_received", transcript=transcript_preview))
        return trim_watch_text(user_copy(locale, "transcript_received", transcript=transcript_preview))

    if stt_error:
        return trim_watch_text(user_copy(locale, "speech_unclear"))

    return user_copy(locale, "audio_processing")


def derive_job_handoff(job: dict) -> bool:
    return classify_handoff_reason(job) is not None


def build_job_watch_summary(job: dict) -> str:
    status = job.get("status")
    if status == "running":
        base = job.get("watch_summary") or user_copy(
            job, "job_running", name=job.get("name") or user_copy(job, "default_task")
        )
        return trim_watch_text(user_copy(
            job, "job_running_elapsed", summary=base, seconds=job.get("elapsed_seconds", 0)
        ))
    if status == "failed":
        stt_error = (job.get("stt_error") or "").strip()
        return trim_watch_text(job.get("watch_summary") or (
            user_copy(job, "command_unclear", error=stt_error) if stt_error else user_copy(job, "job_failed")
        ))
    return trim_watch_text(job.get("watch_summary") or job.get("canned_result") or user_copy(job, "result_ready"))


REPORT_META_FIELDS = (
    "title",
    "status",
    "severity",
    "category",
    "watch_summary",
    "requires_phone_handoff",
    "handoff_reason",
    "phone_report",
    "next_action",
    "retry_count",
    "failure_code",
    "failure_message",
    "outcome",
)

SECTION_FIELDS = (
    "id",
    "title",
    "eyebrow",
    "icon",
    "content",
)

PREVIEW_SECTION_IDS = (
    "category",
    "watch-summary",
    "suggested-next-action",
)


def build_handoff_deep_link(job_id: str | None) -> str | None:
    cleaned = (job_id or "").strip()
    if not cleaned:
        return None
    return f"ceviz://job/{cleaned}"


def derive_job_severity(job: dict) -> str:
    status = (job.get("status") or "").strip().lower()
    outcome = normalize_job_outcome(status, job.get("outcome"))
    if status == "failed" or outcome == "blocked":
        return "high"
    if status in {"running", "processing", "queued"} or outcome == "needs_input":
        return "medium"
    return "low"


def build_handoff_reason(job: dict) -> str | None:
    return classify_handoff_reason(job)


def build_handoff_copy(job: dict) -> str | None:
    reason = build_handoff_reason(job)
    if not reason:
        return None

    key = {
        "needs_clarification": "handoff_needs_clarification",
        "failure_diagnosis": "handoff_failure_diagnosis",
        "approval_required": "handoff_approval_required",
        "too_many_actions": "handoff_too_many_actions",
        "low_confidence": "handoff_low_confidence",
        "logs_and_code": "handoff_logs_and_code",
        "action_required": "handoff_action_required",
        "long_detail": "handoff_long_detail",
        "job_missing": "handoff_job_missing",
    }.get(reason, "handoff_default")
    return user_copy(job, key)


NO_OP_NEXT_ACTION_MARKERS = (
    "işlem gerekmiyor",
    "islem gerekmiyor",
    "ek işlem",
    "ek islem",
    "gerek yok",
    "gerekmiyor",
    "yapılacak bir şey yok",
    "yapilacak bir sey yok",
    "bir şey yapmaya gerek",
    "aksiyon gerekmiyor",
    "herhangi bir işlem",
    "no action",
    "not required",
)


def is_no_op_next_action(text: str) -> bool:
    """Ajan bazen 'Yok.' / 'Ek işlem gerekmiyor.' gibi dolgu cumleleri
    next_action olarak uretiyor ve kendini agent sanip tiklanabilir hale
    getiriyordu; dokununca bu metin komut olarak geri gonderilip kisir
    dongu yaratiyordu. Modele guvenme, deterministik sus."""
    compact = " ".join(clean_text(text).lower().split()).strip(" .!:;")
    if not compact:
        return True
    if compact in {"yok", "none", "-", "n/a", "na", "hayır", "hayir"}:
        return True
    if len(compact) < 12:
        return True
    return any(marker in compact for marker in NO_OP_NEXT_ACTION_MARKERS)


def build_next_actions(job: dict) -> list[dict[str, str | None]]:
    actions: list[dict[str, str | None]] = []
    seen: set[tuple[str, str | None, str]] = set()
    job_id = clean_text(job.get("id"))
    deep_link = build_handoff_deep_link(job_id)
    next_action = clean_text(job.get("next_action"))
    status = clean_text(job.get("status")).lower()

    def append_action(action: dict[str, str | None]) -> None:
        key = (action["kind"] or "", action.get("target"), action["label"] or "")
        if key in seen:
            return
        seen.add(key)
        actions.append(action)

    if derive_job_handoff(job) and deep_link:
        append_action({
            "id": "open-on-phone",
            "label": "Open on Phone",
            "kind": "deeplink",
            "target": deep_link,
        })

    if job_id and status in {"running", "queued"}:
        append_action({
            "id": "summarize-progress",
            "label": "Summarize Progress",
            "kind": "api_call",
            "target": f"/api/v1/jobs/{job_id}/summarize",
        })
        append_action({
            "id": "cancel-job",
            "label": "Stop Job",
            "kind": "api_call",
            "target": f"/api/v1/jobs/{job_id}/cancel",
        })

    for action in get_explicit_next_actions(job):
        append_action(action)

    if next_action and not is_no_op_next_action(next_action):
        append_action({
            "id": "suggested-next-action",
            "label": trim_watch_text(next_action, max_len=80),
            "kind": "agent_command" if job.get("next_action_actor") == "agent" else "hint",
            "target": None,
        })

    return actions


def build_report_meta(job: dict) -> dict:
    meta = {
        "title": (job.get("name") or "OpenClaw Task").strip(),
        "status": (job.get("status") or "unknown").strip(),
        "severity": derive_job_severity(job),
        "category": (job.get("category") or user_copy(job, "default_category")).strip(),
        "watch_summary": build_job_watch_summary(job),
        "requires_phone_handoff": derive_job_handoff(job),
        "handoff_reason": build_handoff_reason(job),
        "phone_report": (job.get("phone_report") or "").strip(),
        "next_action": job.get("next_action") or None,
        "retry_count": job.get("retry_count") or 0,
        "failure_code": job.get("failure_code") or None,
        "failure_message": job.get("failure_message") or None,
        "outcome": normalize_job_outcome(job.get("status"), job.get("outcome")),
    }
    return {field: meta[field] for field in REPORT_META_FIELDS}


def build_section(*, section_id: str, title: str, eyebrow: str, icon: str, content: str) -> dict[str, str]:
    section = {
        "id": section_id,
        "title": title,
        "eyebrow": eyebrow,
        "icon": icon,
        "content": content,
    }
    return {field: section[field] for field in SECTION_FIELDS}


def build_structured_report_fields(job: dict) -> dict:
    return {
        "report_meta": build_report_meta(job),
        "preview_sections": build_preview_sections(job),
    }


def build_common_sections(job: dict) -> list[dict[str, str]]:
    report_meta = build_report_meta(job)
    watch_summary = report_meta["watch_summary"]
    detail = (job.get("phone_report") or job.get("canned_result") or "").strip()

    if job["status"] == "running":
        analysis_content = user_copy(job, "running_analysis", seconds=job["elapsed_seconds"])
        next_action_content = user_copy(job, "running_next")
    elif job["status"] == "failed":
        analysis_content = detail or user_copy(job, "failed_analysis")
        next_action_content = (
            job.get("next_action")
            or user_copy(job, "failed_next")
        )
    else:
        analysis_content = detail or user_copy(job, "completed_analysis")
        next_action_content = (
            job.get("next_action")
            or (
                user_copy(job, "completed_next_with_summary")
                if watch_summary
                else user_copy(job, "completed_next")
            )
        )

    sections: list[dict[str, str]] = []

    category = report_meta["category"]
    if category:
        sections.append(build_section(
            section_id="category",
            title=user_copy(job, "section_category"),
            eyebrow="META",
            icon="tag",
            content=category,
        ))

    if watch_summary:
        sections.append(build_section(
            section_id="watch-summary",
            title=user_copy(job, "section_watch_summary"),
            eyebrow="WATCH",
            icon="applewatch",
            content=watch_summary,
        ))

    sections.append(build_section(
        section_id="expanded-analysis",
        title=user_copy(job, "section_analysis"),
        eyebrow="IPHONE DETAIL",
        icon="text.alignleft",
        content=analysis_content,
    ))

    sections.append(build_section(
        section_id="suggested-next-action",
        title=user_copy(job, "section_next"),
        eyebrow="NEXT",
        icon="arrow.forward.circle",
        content=next_action_content,
    ))

    return sections


def build_report_sections(job: dict) -> list[dict[str, str]]:
    sections = [
        section
        for section in build_common_sections(job)
        if section["id"] != "category"
    ]
    activity = job.get("background_activity") or []
    if activity:
        sections.append(build_section(
            section_id="background-activity",
            title=user_copy(job, "section_activity"),
            eyebrow=user_copy(job, "activity_eyebrow"),
            icon="person.3",
            content="\n".join(activity),
        ))
    return sections


def build_preview_sections(job: dict) -> list[dict[str, str]]:
    common_sections = build_common_sections(job)
    sections = [
        {
            **section,
            "content": trim_watch_text(section["content"], max_len=80 if section["id"] == "category" else 120),
        }
        for section in common_sections
        if section["id"] in PREVIEW_SECTION_IDS
    ]

    if sections:
        return sections

    analysis_section = next((section for section in common_sections if section["id"] == "expanded-analysis"), None)
    if analysis_section:
        return [{
            **analysis_section,
            "content": trim_watch_text(analysis_section["content"], max_len=120),
        }]

    return [build_section(
        section_id="capture",
        title="Capture",
        eyebrow="WATCH",
        icon="waveform.badge.mic",
        content="Transcript unavailable",
    )]



# Rapor iskeleti kullanicinin dilinde uretilir; ajan icerigi zaten
# locale'e gore geliyor, cerceve de ona uymali.
REPORT_STRINGS = {
    "en": {
        "category": "Category", "watch_summary": "Watch summary",
        "handoff": "Hand off to phone", "yes": "Yes", "no": "No",
        "transcript": "Transcript", "none": "None", "stt_source": "STT source",
        "stt_note": "STT note", "running_title": "Job running",
        "running_body": "This job is currently running on OpenClaw.",
        "elapsed": "Elapsed", "seconds": "seconds",
        "refresh_hint": "Tap Refresh to see the latest status.",
        "failed_title": "Failed", "detail": "Detail",
        "no_error_detail": "No error detail available.",
        "report_title": "Report", "result": "Result",
        "no_result": "No result data.",
        "footer": "Note: this report was produced from a real OpenClaw CLI call via the backend.",
    },
    "tr": {
        "category": "Kategori", "watch_summary": "Saat özeti",
        "handoff": "Telefona devret", "yes": "Evet", "no": "Hayır",
        "transcript": "Transkript", "none": "Yok", "stt_source": "STT kaynağı",
        "stt_note": "STT notu", "running_title": "Görev Çalışıyor",
        "running_body": "Görev şu anda OpenClaw üzerinde işleniyor.",
        "elapsed": "Geçen süre", "seconds": "saniye",
        "refresh_hint": "Güncel durumu görmek için Yenile butonuna dokunun.",
        "failed_title": "Hata", "detail": "Detay",
        "no_error_detail": "Hata detayı bulunamadı.",
        "report_title": "Rapor", "result": "İşlem Sonucu",
        "no_result": "Sonuç verisi bulunamadı.",
        "footer": "Not: Bu rapor backend üzerinden gerçek OpenClaw CLI çağrısının çıktısından üretildi.",
    },
}


def report_strings(job: dict) -> dict:
    locale = str(job.get("locale") or "").strip()
    code = locale.replace("_", "-").split("-")[0].lower() if locale else "en"
    return REPORT_STRINGS.get(code, REPORT_STRINGS["en"])


def build_job_report(job: dict) -> tuple[str, str]:
    t = report_strings(job)
    report_meta = build_report_meta(job)
    category_text = f"[{report_meta['category']}]"
    watch_summary = report_meta["watch_summary"]
    requires_phone_handoff = report_meta["requires_phone_handoff"]
    transcript = (job.get("transcript") or "").strip() or t["none"]
    stt_source = job.get("stt_source") or "unknown"
    stt_error = (job.get("stt_error") or "").strip()
    elapsed = f"{t['elapsed']}: {job['elapsed_seconds']} {t['seconds']}."

    meta_lines = [
        f"{t['category']}: {category_text}",
        f"{t['watch_summary']}: {watch_summary}",
        f"{t['handoff']}: {t['yes'] if requires_phone_handoff else t['no']}",
        f"{t['transcript']}: {transcript}",
        f"{t['stt_source']}: {stt_source}",
    ]
    if stt_error:
        meta_lines.append(f"{t['stt_note']}: {stt_error}")

    if job["status"] == "running":
        return (
            f"{t['running_title']}: {job['name']}",
            "\n".join(meta_lines)
            + f"\n\n{t['running_body']}\n{elapsed}\n\n{t['refresh_hint']}",
        )

    if job["status"] == "failed":
        detail = job.get("phone_report") or job.get("canned_result") or t["no_error_detail"]
        return (
            f"{t['failed_title']}: {job['name']}",
            "\n".join(meta_lines)
            + f"\n\n{t['detail']}:\n"
            + detail
            + f"\n\n{elapsed}",
        )

    detail = job.get("phone_report") or job.get("canned_result") or t["no_result"]
    return (
        f"{t['report_title']}: {job['name']}",
        "\n".join(meta_lines)
        + f"\n\n{t['result']}:\n"
        + detail
        + f"\n\n{elapsed}\n\n{t['footer']}",
    )


def sync_job_status(job: dict) -> None:
    now = time.time()
    previous_status = job.get("status")
    job["elapsed_seconds"] = max(0, int(now - job["created_at"]))
    try:
        _sync_job_status_impl(job, now)
    finally:
        # Durum degistiyse gecmisi diske yaz (running -> completed/failed).
        if job.get("status") != previous_status:
            save_jobs()


def _sync_job_status_impl(job: dict, now: float) -> None:
    invocation = job.get("invocation")
    if not invocation or job["status"] not in {"running", "processing"}:
        return

    process = invocation["process"]
    return_code = process.poll()
    if return_code is None:
        job["status"] = "running"
        return

    if return_code == 0:
        try:
            result = openclaw_client.extract_result(invocation["log_path"], locale=job.get("locale", ""))
            try:
                job["background_activity"] = openclaw_client.collect_background_activity(
                    invocation["started_at"], invocation["log_path"], locale=job.get("locale", "")
                )
            except Exception:
                job["background_activity"] = []
            apply_task_result(job, result)
        except Exception as exc:
            logging.exception("Failed to parse OpenClaw result for job %s", job["id"])
            if locale_code(job) == "en":
                detail = (
                    "The OpenClaw call ended, but its response could not be parsed.\n\n"
                    f"Error: {exc}\n\nLog excerpt:\n{openclaw_client.read_log_tail(invocation['log_path'])}"
                )
            else:
                detail = (
                    "OpenClaw çağrısı tamamlandı ama yanıt çözümlenemedi.\n\n"
                    f"Hata: {exc}\n\nLog özeti:\n{openclaw_client.read_log_tail(invocation['log_path'])}"
                )
            mark_result_unconfirmed(job, detail)
        return

    if locale_code(job) == "en":
        detail = (
            f"The OpenClaw call exited with code {return_code}. Its task outcome is unconfirmed.\n\n"
            f"Log excerpt:\n{openclaw_client.read_log_tail(invocation['log_path'])}"
        )
    else:
        detail = (
            f"OpenClaw çağrısı {return_code} koduyla sonlandı. Görev sonucu doğrulanamadı.\n\n"
            f"Log özeti:\n{openclaw_client.read_log_tail(invocation['log_path'])}"
        )
    mark_result_unconfirmed(job, detail)


def apply_task_result(job: dict, result: TaskResult) -> None:
    # Publish the terminal lifecycle with its report, never before it: the push
    # monitor and request handler can observe the same job concurrently.
    job.update(
        category=result.category, canned_result=result.canned_result,
        watch_summary=result.watch_summary, requires_phone_handoff=result.requires_phone_handoff,
        phone_report=result.phone_report, next_action=result.next_action,
        outcome=normalize_job_outcome("completed", result.outcome),
        next_action_actor=result.next_action_actor, status="completed",
    )


def mark_result_unconfirmed(job: dict, detail: str, summary: str | None = None) -> None:
    job.update(
        canned_result=detail, phone_report=detail,
        watch_summary=summary or user_copy(job, "result_unconfirmed"),
        requires_phone_handoff=True, next_action=user_copy(job, "check_before_retry"),
        next_action_actor="user", outcome="unknown", status="failed",
    )


def _serializable_job(job: dict) -> dict:
    """Popen nesnesi JSON'a yazilamaz; invocation'in geri kalanini koru
    (log_path sayesinde servis kapaliyken biten is kurtarilabilir)."""
    out = {k: v for k, v in job.items() if k != "invocation"}
    invocation = job.get("invocation")
    if isinstance(invocation, dict):
        out["invocation"] = {
            k: v for k, v in invocation.items() if k != "process"
        }
    return out


def save_jobs() -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        recent = sorted(jobs_db.values(), key=lambda j: j.get("created_at", 0))[-MAX_PERSISTED_JOBS:]
        payload = {"jobs": [_serializable_job(job) for job in recent]}
        tmp = JOBS_STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(JOBS_STATE_PATH)
    except Exception as exc:
        logging.warning("İş geçmişi yazılamadı: %s", exc)


def load_jobs() -> None:
    """Diskteki gecmisi geri yukle. Servis kapaliyken tamamlanmis
    olabilecek isleri log dosyasindan sonuclandirmayi dene."""
    if not JOBS_STATE_PATH.exists():
        return
    try:
        data = json.loads(JOBS_STATE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.warning("İş geçmişi okunamadı: %s", exc)
        return

    restored = 0
    recovered = 0
    state_changed = False
    for job in data.get("jobs", []):
        if not isinstance(job, dict) or not job.get("id"):
            continue
        invocation = job.get("invocation")
        if job.get("status") in {"running", "processing", "queued"}:
            state_changed = True
            log_path = (invocation or {}).get("log_path")
            result = None
            if log_path and Path(log_path).exists():
                try:
                    result = openclaw_client.extract_result(log_path, locale=job.get("locale", ""))
                except Exception:
                    result = None
            if result is not None:
                apply_task_result(job, result)
                recovered += 1
            else:
                mark_result_unconfirmed(
                    job, user_copy(job, "backend_restart_report"), user_copy(job, "backend_restart_summary")
                )
        # Yeniden baslatma sonrasi canli process yok.
        job.pop("invocation", None)
        jobs_db[job["id"]] = job
        restored += 1

    if restored:
        logging.info("İş geçmişi yüklendi: %d iş (%d tanesi loglardan kurtarıldı)", restored, recovered)
    if state_changed:
        # Yeniden baslatmada canli process'i olmayan islerin duzeltilmis
        # durumunu hemen kalicilastir; sonraki acilista hayalet running olmasin.
        save_jobs()


def build_continuation_context(prev_job: dict, *, approved_suggestion: bool) -> str:
    prev_summary = trim_watch_text(prev_job.get("watch_summary") or prev_job.get("canned_result") or "", 220)
    if approved_suggestion:
        directive = (
            "Kullanıcı, önceki işin raporundaki öneriyi UYGULAMANI ONAYLADI; transkript o önerinin metnidir. "
            "Bağlamı kullanarak istenen işlemi ŞİMDİ gerçekleştir; tekrar teyit isteme."
        )
    else:
        directive = (
            "Bu komut muhtemelen az önceki işin devamı. Yeni komut önceki bağlamla İLİŞKİLİYSE bağlamı kullan; "
            "ilişkisizse bağımsız yeni komut olarak ele al. Transkript bozuksa işlem yapma, onay iste."
        )
    return (
        "BAĞLAM (devam eden konuşma):\n"
        f"- Önceki komut: {trim_watch_text(prev_job.get('transcript') or prev_job.get('name') or '', 160)}\n"
        f"- Önceki sonucun özeti: {prev_summary}\n"
        f"- {directive}"
    )


def create_openclaw_job(
    *,
    transcript: str,
    source: str,
    client_timestamp: str | None = None,
    stt_error: str = "",
    continue_job: dict | None = None,
    approved_suggestion: bool = False,
    locale: str = "",
) -> dict:
    effective_transcript = transcript.strip()

    # Konusma surekliligi: acik devam (oneri onayi) veya son isten 180 sn
    # icinde gelen komut ayni konusmanin devami sayilir; onceki isin
    # baglami prompt'a eklenir ki ajan ipin ucunu kaybetmesin.
    conversation_id = uuid.uuid4().hex[:8]
    if continue_job is None and jobs_db:
        last_job = max(jobs_db.values(), key=lambda j: j["created_at"])
        if time.time() - last_job["created_at"] < 180:
            continue_job = last_job
    if continue_job is not None:
        conversation_id = continue_job.get("conversation_id", conversation_id)

    invocation_payload = {
        "audio_data": "",
        "format": source,
        "client_timestamp": client_timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "transcript": effective_transcript,
        "_stt_source": source,
        "_stt_error": stt_error,
        "locale": locale,
    }
    if continue_job is not None:
        invocation_payload["_continuation_context"] = build_continuation_context(
            continue_job, approved_suggestion=approved_suggestion
        )
    new_job_id = f"job-{uuid.uuid4().hex[:8]}"
    try:
        invocation = openclaw_client.invoke_watch_command(invocation_payload)
    except OpenClawUnavailable as exc:
        # Kurulum hatasi: isi 500 ile dusurme, konusan bir "failed" is uret
        # ki kullanici saatte/telefonda sebebini gorsun.
        logging.error("OpenClaw çağrılamadı: %s", exc)
        failed_job = {
            "id": new_job_id,
            "conversation_id": conversation_id,
            "locale": locale,
            "name": effective_transcript or user_copy(locale, "command_name"),
            "status": "failed",
            "created_at": time.time(),
            "elapsed_seconds": 0,
            "category": user_copy(locale, "install_category"),
            "canned_result": str(exc),
            "watch_summary": trim_watch_text(str(exc), 160),
            "requires_phone_handoff": True,
            "phone_report": str(exc),
            "transcript": effective_transcript,
            "stt_source": source,
            "stt_error": stt_error,
            "next_action": None,
            "outcome": "blocked",
            "next_action_actor": None,
        }
        jobs_db[new_job_id] = failed_job
        save_jobs()
        return failed_job
    initial_requires_phone_handoff = not bool(effective_transcript)
    summary_text = build_processing_summary(source, effective_transcript, stt_error, locale)
    phone_report = (
        user_copy(locale, "openclaw_started")
        if effective_transcript
        else user_copy(locale, "openclaw_started_no_transcript")
    )

    job = {
        "id": new_job_id,
        "conversation_id": conversation_id,
        "locale": locale,
        "name": effective_transcript or client_timestamp or "Shortcut Command",
        "status": "running",
        "created_at": time.time(),
        "elapsed_seconds": 0,
        "category": user_copy(locale, "default_category"),
        "canned_result": user_copy(locale, "openclaw_waiting"),
        "watch_summary": summary_text,
        "requires_phone_handoff": initial_requires_phone_handoff,
        "phone_report": phone_report,
        "transcript": effective_transcript,
        "stt_source": source,
        "stt_error": stt_error,
        "next_action": None,
        "invocation": {
            "process": invocation.process,
            "log_path": invocation.log_path,
            "prompt": invocation.prompt,
            "command": invocation.command,
            "started_at": invocation.started_at,
        },
    }
    jobs_db[new_job_id] = job
    save_jobs()
    return job


def build_watch_command_response(job: dict) -> dict:
    structured_fields = build_structured_report_fields(job)
    requires_phone_handoff = derive_job_handoff(job)
    resp_payload = {
        "status": job["status"] if job["status"] in {"completed", "failed"} else "processing",
        "outcome": structured_fields["report_meta"]["outcome"],
        "transcript": (job.get("transcript") or "").strip(),
        "summary_text": build_job_watch_summary(job),
        "tts_audio_data": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=",
        "tts_format": "aac",
        "requires_phone_handoff": requires_phone_handoff,
        "handoff_reason": build_handoff_reason(job),
        "job_id": job["id"],
        "phone_report": job.get("phone_report") or "",
        "next_actions": build_next_actions(job),
        **structured_fields,
    }
    if requires_phone_handoff:
        deep_link = build_handoff_deep_link(job["id"])
        resp_payload["deep_link"] = deep_link
        resp_payload["handoff_url"] = deep_link
    return resp_payload


def build_shortcut_response(job: dict) -> dict:
    sync_job_status(job)
    summary = build_job_watch_summary(job)
    job_id = job["id"]
    return {
        "status": job.get("status", "unknown"),
        "outcome": normalize_job_outcome(job.get("status"), job.get("outcome")),
        "done": job.get("status") in {"completed", "failed"},
        "job_id": job_id,
        "transcript": (job.get("transcript") or "").strip(),
        "summary": summary,
        "shortcut_text": summary,
        "requires_phone_handoff": derive_job_handoff(job),
        "handoff_reason": build_handoff_reason(job),
        "phone_report": job.get("phone_report") or "",
        "next_action": job.get("next_action") or None,
        "poll_url": f"/api/v1/shortcuts/jobs/{job_id}",
        "report_url": f"/api/v1/jobs/{job_id}/report",
    }


def parse_shortcut_text(payload: dict | str) -> tuple[str, str | None]:
    if isinstance(payload, str):
        return payload.strip(), None

    for key in ("text", "prompt", "transcript", "command"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), payload.get("client_timestamp")

    return "", payload.get("client_timestamp")


def parse_wait_seconds(payload: dict | str, query: dict[str, list[str]]) -> float:
    raw_value = None
    if isinstance(payload, dict):
        raw_value = payload.get("wait_seconds")
    if raw_value is None and "wait" in query:
        raw_value = query["wait"][0]
    if raw_value is None and "wait_seconds" in query:
        raw_value = query["wait_seconds"][0]

    try:
        wait_seconds = float(raw_value)
    except (TypeError, ValueError):
        return 0

    return max(0, min(wait_seconds, 45))


def wait_for_job_completion(job: dict, timeout_seconds: float, poll_interval: float = 1.0) -> None:
    if timeout_seconds <= 0:
        return

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        sync_job_status(job)
        if job.get("status") in {"completed", "failed"}:
            return
        time.sleep(poll_interval)

    sync_job_status(job)


class WatchCevizHandler(BaseHTTPRequestHandler):
    def _authorized(self) -> bool:
        if not AUTH_TOKEN:
            return True
        header = self.headers.get("Authorization", "")
        return hmac.compare_digest(header, f"Bearer {AUTH_TOKEN}")

    def _reject_unauthorized(self, path: str) -> bool:
        if not path.startswith("/api/") or self._authorized():
            return False
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error": "Unauthorized"}')
        return True

    def do_GET(self):
        import traceback
        try:
            self._do_GET_impl()
        except Exception as exc:
            logging.error("GET %s başarısız: %s", self.path, exc)
            traceback.print_exc()
            try:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))
            except Exception:
                pass

    def _do_GET_impl(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if self._reject_unauthorized(path):
            return
        if path in {"/", "/shortcuts", "/api/v1/shortcuts/command"}:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Watch Ceviz Shortcuts</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; line-height: 1.45; max-width: 760px; }
    code, pre { background: #f4f4f5; border-radius: 6px; }
    code { padding: 2px 5px; }
    pre { padding: 14px; overflow-x: auto; }
    .ok { color: #166534; font-weight: 700; }
  </style>
</head>
<body>
  <h1>Watch Ceviz Shortcuts backend</h1>
  <p class="ok">The backend is running.</p>
  <p>This page is for status and setup only. Shortcut commands are sent as POST requests, not browser GET requests.</p>
  <h2>Shortcut URL</h2>
  <pre>POST /api/v1/shortcuts/command
Content-Type: application/json

{"text":"summarize today's jobs","wait_seconds":25,"locale":"en-US"}</pre>
  <h2>Poll URL</h2>
  <pre>GET /api/v1/shortcuts/jobs/&lt;job_id&gt;</pre>
  <h2>Health</h2>
  <p><a href="/api/v1/jobs/active">/api/v1/jobs/active</a></p>
</body>
</html>""")
        elif path == "/api/v1/jobs/active":
            active_jobs = []
            for jid, job in list(jobs_db.items()):
                sync_job_status(job)
                structured_fields = build_structured_report_fields(job)
                deep_link = build_handoff_deep_link(job["id"]) if derive_job_handoff(job) else None
                active_jobs.append({
                    "id": job["id"],
                    "conversation_id": job.get("conversation_id") or "",
                    "name": job["name"],
                    "status": job["status"],
                    "outcome": structured_fields["report_meta"]["outcome"],
                    "elapsed_seconds": job["elapsed_seconds"],
                    "summary_text": build_job_watch_summary(job),
                    "requires_phone_handoff": derive_job_handoff(job),
                    "transcript": (job.get("transcript") or "").strip(),
                    "phone_report": job.get("phone_report") or "",
                    "next_actions": build_next_actions(job),
                    **structured_fields,
                    **({"deep_link": deep_link} if deep_link else {}),
                })

            resp_payload = {
                "jobs": active_jobs
            }

            resp_schema = load_contract("active-jobs-response.schema.json")
            resp_errors = validate_payload(resp_payload, resp_schema)
            if resp_errors:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Response validation failed", "details": resp_errors}).encode("utf-8"))
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp_payload).encode("utf-8"))
        elif path.startswith("/api/v1/jobs/") and path.endswith("/report"):
            job_id = path.split("/")[4]
            now = time.time()

            job = jobs_db.get(job_id)
            if not job:
                job = {
                    "id": job_id,
                    "name": "Unknown Task",
                    "locale": "en",
                    "status": "missing",
                    "created_at": now - 30,
                    "elapsed_seconds": 30,
                    "category": user_copy("en", "unknown_category"),
                    "canned_result": user_copy("en", "detail_missing"),
                    "watch_summary": user_copy("en", "task_missing"),
                    "requires_phone_handoff": True,
                    "phone_report": user_copy("en", "detail_missing"),
                    "transcript": "",
                    "stt_source": "unknown",
                    "stt_error": "",
                    "next_action": None,
                }
            else:
                sync_job_status(job)

            report_title, report_content = build_job_report(job)
            structured_fields = build_structured_report_fields(job)
            deep_link = build_handoff_deep_link(job_id) if derive_job_handoff(job) else None
            resp_payload = {
                "job_id": job_id,
                "conversation_id": job.get("conversation_id") or "",
                "status": job["status"],
                "outcome": structured_fields["report_meta"]["outcome"],
                "report_title": report_title,
                "report_content": report_content,
                "report_sections": build_report_sections(job),
                "watch_summary": build_job_watch_summary(job),
                "requires_phone_handoff": derive_job_handoff(job),
                "handoff_reason": build_handoff_reason(job),
                "next_action": job.get("next_action") or None,
                "next_actions": build_next_actions(job),
                **structured_fields,
            }
            if deep_link:
                resp_payload["deep_link"] = deep_link

            resp_schema = load_contract("job-report-response.schema.json")
            resp_errors = validate_payload(resp_payload, resp_schema)
            if resp_errors:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Response validation failed", "details": resp_errors}).encode("utf-8"))
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp_payload).encode("utf-8"))
        elif path.startswith("/api/v1/shortcuts/jobs/"):
            job_id = path.split("/")[5]
            job = jobs_db.get(job_id)
            if not job:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "Job not found",
                    "job_id": job_id,
                    "shortcut_text": f"Job {job_id} was not found.",
                }).encode("utf-8"))
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(build_shortcut_response(job)).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error": "Not found"}')

    def do_POST(self):
        import traceback
        try:
            self._do_POST_impl()
        except Exception as e:
            print(f"ERROR: {e}", flush=True)
            traceback.print_exc()
            self.send_response(500)
            self.end_headers()
    def _do_POST_impl(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query)
        if self._reject_unauthorized(path):
            return
        if path == "/api/v1/push/register":
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            try:
                result = push_notifier.register(payload)
                status = 200
            except Exception as exc:
                logging.exception("Push registration failed")
                result = {"ok": False, "error": str(exc)}
                status = 502
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        if path.startswith("/api/v1/jobs/") and path.endswith("/cancel"):
            job_id = path.split("/")[4]
            job = jobs_db.get(job_id)
            if job:
                sync_job_status(job)
                invocation = job.get("invocation")
                if invocation and invocation["process"].poll() is None:
                    invocation["process"].terminate()
                    mark_result_unconfirmed(job, user_copy(job, "job_cancelled"), user_copy(job, "job_cancelled"))
                    save_jobs()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "cancelled", "job_id": job_id}).encode("utf-8"))
            return
        elif path.startswith("/api/v1/jobs/") and path.endswith("/summarize"):
            job_id = path.split("/")[4]
            job = jobs_db.get(job_id)
            if not job:
                summary = f"Job {job_id} was not found."
                requires_phone_handoff = True
                handoff_url = None
                deep_link = None
                job_status = "missing"
                handoff_reason = "job_missing"
                next_actions = []
            else:
                sync_job_status(job)
                summary = build_job_watch_summary(job)
                requires_phone_handoff = derive_job_handoff(job)
                deep_link = build_handoff_deep_link(job_id) if requires_phone_handoff else None
                handoff_url = deep_link
                job_status = job.get("status", "unknown")
                structured_fields = build_structured_report_fields(job)
                handoff_reason = build_handoff_reason(job)
                next_actions = build_next_actions(job)
                report_meta = structured_fields["report_meta"]
                preview_sections = structured_fields["preview_sections"]

            response_payload = {
                "summary": summary,
                "requires_phone_handoff": requires_phone_handoff,
                "status": job_status,
                "outcome": normalize_job_outcome(job_status, job.get("outcome") if job else None),
                "transcript": (job.get("transcript") or "").strip() if job else "",
                "phone_report": (job.get("phone_report") or "") if job else "",
                "handoff_reason": handoff_reason,
                "next_actions": next_actions,
                "report_meta": report_meta if job else build_report_meta({
                    "status": "missing",
                    "locale": "en",
                    "category": user_copy("en", "default_category"),
                    "watch_summary": summary,
                    "phone_report": summary,
                    "name": "Unknown Task"
                }),
                "preview_sections": preview_sections if job else build_preview_sections({
                    "status": "missing",
                    "locale": "en",
                    "category": user_copy("en", "default_category"),
                    "watch_summary": summary,
                    "phone_report": summary,
                }),
            }
            if deep_link:
                response_payload["deep_link"] = deep_link
            if handoff_url:
                response_payload["handoff_url"] = handoff_url

            resp_schema = load_contract("job-summary-response.schema.json")
            resp_errors = validate_payload(response_payload, resp_schema)
            if resp_errors:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Response validation failed", "details": resp_errors}).encode("utf-8"))
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_payload).encode("utf-8"))
            return
        elif path == "/api/v1/shortcuts/command":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            content_type = self.headers.get("Content-Type", "")

            if "application/json" in content_type:
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"error": "Invalid JSON"}')
                    return
            else:
                payload = body.decode("utf-8", errors="replace")

            transcript, client_timestamp = parse_shortcut_text(payload)
            if not transcript:
                request_locale = str(payload.get("locale") or "") if isinstance(payload, dict) else ""
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "Missing shortcut text",
                    "shortcut_text": user_copy(request_locale, "shortcut_missing"),
                }).encode("utf-8"))
                return

            continue_job = None
            approved_suggestion = False
            if isinstance(payload, dict):
                continue_job = jobs_db.get(str(payload.get("continue_job_id") or ""))
                approved_suggestion = continue_job is not None

            job = create_openclaw_job(
                transcript=transcript,
                source="shortcut",
                client_timestamp=client_timestamp,
                continue_job=continue_job,
                approved_suggestion=approved_suggestion,
                locale=str(payload.get("locale") or "") if isinstance(payload, dict) else "",
            )
            wait_for_job_completion(job, parse_wait_seconds(payload, query))

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(build_shortcut_response(job)).encode("utf-8"))
            return
        elif path == "/api/v1/watch/command":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error": "Invalid JSON"}')
                return

            req_schema = load_contract("watch-command-request.schema.json")
            errors = validate_payload(payload, req_schema)
            if errors:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Validation failed", "details": errors}).encode("utf-8"))
                return

            audio_fingerprint = hashlib.sha256(payload["audio_data"].encode("utf-8")).hexdigest()
            duplicate_job = next(
                (
                    candidate
                    for candidate in sorted(
                        jobs_db.values(), key=lambda item: item.get("created_at", 0), reverse=True
                    )
                    if candidate.get("audio_fingerprint") == audio_fingerprint
                    and time.time() - candidate.get("created_at", 0) < 30 * 60
                ),
                None,
            )
            if duplicate_job is not None:
                logging.warning("Duplicate watch audio suppressed; returning %s", duplicate_job["id"])
                sync_job_status(duplicate_job)
                resp_payload = build_watch_command_response(duplicate_job)
            else:
                stt_result = stt_client.transcribe_watch_payload(payload)
                effective_transcript = stt_result.transcript.strip()
                job = create_openclaw_job(
                    transcript=effective_transcript,
                    source=stt_result.source,
                    client_timestamp=payload.get("client_timestamp"),
                    stt_error=stt_result.error or "",
                    locale=str(payload.get("locale") or ""),
                )
                job["audio_fingerprint"] = audio_fingerprint
                save_jobs()
                resp_payload = build_watch_command_response(job)

            resp_schema = load_contract("watch-command-response.schema.json")
            resp_errors = validate_payload(resp_payload, resp_schema)
            if resp_errors:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Response validation failed", "details": resp_errors}).encode("utf-8"))
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp_payload).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error": "Not found"}')


def _warmup_stt() -> None:
    try:
        import local_whisper
        device = local_whisper.warmup()
        logging.info("STT warmup tamam (cihaz=%s, model=%s)", device,
                     os.environ.get("WATCH_CEVIZ_WHISPER_MODEL", "small"))
    except Exception as exc:
        logging.warning("STT warmup atlandı: %s", exc)

def _monitor_jobs_for_push() -> None:
    """Observe terminal transitions even while the phone and watch are suspended."""
    while True:
        try:
            for job in list(jobs_db.values()):
                sync_job_status(job)
                try:
                    if push_notifier.notify_terminal_job(job):
                        save_jobs()
                except Exception as exc:
                    logging.warning("Push delivery deferred for %s: %s", job.get("id"), exc)
        except Exception:
            logging.exception("Push monitor iteration failed")
        time.sleep(5)



def run(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, WatchCevizHandler)
    logging.info(f"Starting watch-ceviz stub server on port {port}...")
    load_jobs()
    # Modeli arka planda onden yukle: server hemen ayakta, ilk komut hizli.
    import threading
    threading.Thread(target=_warmup_stt, daemon=True).start()
    threading.Thread(target=_monitor_jobs_for_push, daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
    logging.info("Server stopped.")


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run(port)
