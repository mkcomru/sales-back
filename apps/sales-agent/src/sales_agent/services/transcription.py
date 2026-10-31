"""Audio transcription service for converting audio attachments to text.

This module provides a transcription service abstraction that is independent
from the LLM service. This allows switching dialog generation to Claude (or others)
while keeping OpenAI for transcription.
"""

import asyncio
import io
import time
from typing import Any, Protocol

import httpx
import structlog
from openai import AsyncOpenAI

from common import SalesAgentSettings

from src.sales_agent.services.backend_client import BackendClient
from src.sales_agent.services.debounce import IncomingMessage

log = structlog.get_logger()


class TranscriptionError(Exception):
    """Raised when transcription fails."""

    pass


class TranscriptionProvider(Protocol):
    """Protocol interface for transcription providers.

    This abstraction allows different transcription vendors (OpenAI, etc.)
    to be used independently from the LLM service.
    """

    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        filename: str | None,
        mime: str | None,
        duration_s: float | None = None,
    ) -> str:
        """Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw audio file bytes
            filename: Original filename (for hinting)
            mime: MIME type if known
            duration_s: Audio duration in seconds if available

        Returns:
            Transcript text

        Raises:
            TranscriptionError: If transcription fails
        """
        ...  # pragma: no cover - protocol only


class OpenAITranscriptionService:
    """OpenAI-based transcription service (Whisper or gpt-4o-mini-transcribe).

    This service uses dedicated configuration from `settings.audio` which is
    independent from the LLM service configuration (`settings.llm`). This allows
    switching dialog generation to Claude or other providers while keeping OpenAI
    for transcription.

    Currently, the provider is fixed to OpenAI. The configuration supports:
    - Custom base URL override (for OpenAI-compatible APIs)
    - Separate API key (not shared with LLM)
    - Model selection (gpt-4o-mini-transcribe or whisper-1)
    - Timeout and size limits
    """

    def __init__(self, settings: SalesAgentSettings):
        self.settings = settings
        # AICODE-NOTE: Use dedicated audio config, not LLM config
        # This allows independent configuration of transcription vs generation
        self.audio_config = settings.audio
        # AICODE-NOTE: Default to OpenAI API;
        # allow base_url override for compatible endpoints
        base_url = self.audio_config.base_url or "https://api.openai.com/v1"
        self.api_key = self.audio_config.api_key
        self.model = self.audio_config.model
        self.timeout_s = self.audio_config.timeout_s
        # Initialize official OpenAI Python async client
        self._client = AsyncOpenAI(
            api_key=(self.api_key.get_secret_value() if self.api_key else None),
            base_url=base_url,
            timeout=httpx.Timeout(self.timeout_s),
        )

    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        filename: str | None,
        mime: str | None,
        duration_s: float | None = None,
    ) -> str:
        """Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw audio file bytes
            filename: Original filename (for hinting)
            mime: MIME type if known
            duration_s: Audio duration in seconds if available

        Returns:
            Transcript text

        Raises:
            TranscriptionError: If transcription fails
        """
        if not self.api_key:
            raise TranscriptionError("Audio transcription API key not configured")

        start_time = time.perf_counter()
        log.info(
            "transcription.started",
            filename=filename,
            mime=mime,
            size_bytes=len(audio_bytes),
            duration_s=duration_s,
            model=self.model,
        )

        # Optional pre-transcode for formats that often fail server-side
        if self.audio_config.transcode_enabled and _should_transcode(mime, filename):
            try:
                audio_bytes = await _transcode_to_wav(
                    audio_bytes,
                    ffmpeg_path=self.audio_config.ffmpeg_path,
                    timeout_s=self.audio_config.timeout_s,
                )
                filename = (filename or "audio").rsplit(".", 1)[0] + ".wav"
                mime = "audio/wav"
                log.info(
                    "transcription.transcoded",
                    filename=filename,
                    target_mime=mime,
                    size_bytes=len(audio_bytes),
                )
            except Exception as e:
                log.warning(
                    "transcription.transcode_failed",
                    filename=filename,
                    error=str(e),
                )

        # Prepare file-like object for SDK
        file_like = io.BytesIO(audio_bytes)
        file_like.name = filename or "audio.ogg"
        try:
            result = await self._client.audio.transcriptions.create(
                model=self.model,
                file=file_like,
            )

            transcript_text = (getattr(result, "text", None) or "").strip()

            latency_ms = int((time.perf_counter() - start_time) * 1000)
            log.info(
                "transcription.succeeded",
                filename=filename,
                mime=mime,
                size_bytes=len(audio_bytes),
                duration_s=duration_s,
                model=self.model,
                latency_ms=latency_ms,
                transcript_length=len(transcript_text),
            )

            return transcript_text

        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            log.error(
                "transcription.failed",
                filename=filename,
                mime=mime,
                size_bytes=len(audio_bytes),
                duration_s=duration_s,
                model=self.model,
                latency_ms=latency_ms,
                error=str(e),
            )
            raise TranscriptionError(f"Transcription failed: {e}") from e


# AICODE-NOTE: TranscriptionService is currently fixed to OpenAI provider
# Future providers can implement TranscriptionProvider protocol
TranscriptionService = OpenAITranscriptionService


class AudioAttachmentCollector:
    """Collects audio attachments from message batch."""

    def collect(self, batch: list[IncomingMessage]) -> list[tuple[IncomingMessage, dict[str, Any]]]:
        """Collect all audio attachments from batch (latest first)."""
        audio_attachments: list[tuple[IncomingMessage, dict[str, Any]]] = []
        for msg in reversed(batch):
            if not msg.attachments:
                continue
            for att in msg.attachments:
                if att.get("type") in ("voice", "audio"):
                    audio_attachments.append((msg, att))
        return audio_attachments


class TranscriptionCache:
    """Handles transcription cache operations with Backend."""

    def __init__(self, backend_client: BackendClient | None):
        self.backend_client = backend_client

    async def get_cached(self, message_id: str | None) -> str | None:
        """Get cached transcription from Backend."""
        if not self.backend_client or not message_id:
            return None

        try:
            message_data = await self.backend_client.get_message_by_id(message_id)
            raw = message_data.get("transcription") or message_data.get("content") or ""
            cached_text = raw.strip() or None
            if cached_text:
                return cached_text
        except Exception as e:
            log.debug(
                "transcription.cache_lookup_failed",
                message_id=message_id,
                error=str(e),
            )
        return None

    async def save(self, message_id: str | None, text: str, artifact_id: str) -> None:
        """Save transcription to Backend cache."""
        if not self.backend_client or not message_id:
            if self.backend_client and not message_id:
                log.warning(
                    "transcription.message_id_not_found",
                    artifact_id=artifact_id,
                )
            return

        try:
            await self.backend_client.save_transcription(message_id, text)
            log.info(
                "transcription.saved_to_backend",
                message_id=message_id,
                artifact_id=artifact_id,
            )
        except Exception as e:
            log.warning(
                "transcription.save_failed",
                message_id=message_id,
                artifact_id=artifact_id,
                error=str(e),
            )


class AudioFileDownloader:
    """Downloads and validates audio files from S3."""

    def __init__(self, backend_client: BackendClient | None, config: Any):
        self.backend_client = backend_client
        self.config = config

    async def download_and_validate(
        self,
        artifact_id: str,
        mime: str | None,
    ) -> bytes | None:
        """Download audio file and validate MIME type."""
        if not self.backend_client:
            log.warning(
                "transcription.backend_client_missing",
                artifact_id=artifact_id,
            )
            return None

        if mime and mime not in self.config.supported_mimes:
            log.warning(
                "transcription.unsupported_mime",
                artifact_id=artifact_id,
                mime=mime,
                supported=self.config.supported_mimes,
            )
            return None

        try:
            audio_bytes = await self.backend_client.download_artifact(artifact_id)
        except Exception as e:
            log.error(
                "transcription.download_failed",
                artifact_id=artifact_id,
                error=str(e),
            )
            return None

        return audio_bytes


class TranscriptionProcessor:
    """Processes single audio attachment: transcribe and save."""

    def __init__(
        self,
        service: TranscriptionProvider,
        cache: TranscriptionCache,
        downloader: AudioFileDownloader,
        config: Any,
    ):
        self.service = service
        self.cache = cache
        self.downloader = downloader
        self.config = config

    async def process(
        self,
        msg: IncomingMessage,
        att: dict[str, Any],
    ) -> bool:
        """Process single attachment. Returns True if transcription succeeded."""
        artifact_id = att.get("artifact_id")
        if not artifact_id:
            log.warning(
                "transcription.missing_artifact_id",
                attachment=att,
            )
            return False

        filename = att.get("filename") or artifact_id.split("/")[-1]
        mime = att.get("mime")
        message_id = msg.metadata.get("backend_message_id")

        if not message_id and self.cache.backend_client:
            log.warning(
                "transcription.backend_message_id_missing",
                artifact_id=artifact_id,
                metadata_keys=list(msg.metadata.keys()),
            )

        cached_text = await self.cache.get_cached(message_id)
        if cached_text:
            log.info(
                "transcription.cache_hit",
                artifact_id=artifact_id,
                message_id=message_id,
            )
            if msg.text:
                msg.text = f"{msg.text}\n{cached_text}"
            else:
                msg.text = cached_text
            return True

        audio_bytes = await self.downloader.download_and_validate(artifact_id, mime)
        if not audio_bytes:
            return False

        if len(audio_bytes) > self.config.max_audio_bytes:
            log.warning(
                "transcription.size_exceeded",
                filename=filename,
                mime=mime,
                size_bytes=len(audio_bytes),
                max_bytes=self.config.max_audio_bytes,
            )
            fallback_text = (
                "Извините, аудиофайл слишком большой для обработки. "
                "Пожалуйста, отправьте аудио меньшего размера или напишите текстом."
            )
            if msg.text:
                msg.text = f"{msg.text}\n{fallback_text}"
            else:
                msg.text = fallback_text
            return False

        duration_s = att.get("duration_s")
        if duration_s is None:
            duration_s = att.get("duration")
        if duration_s is not None:
            try:
                duration_s = float(duration_s)
            except (ValueError, TypeError):
                duration_s = None

        transcript_text = await self.service.transcribe(
            audio_bytes=audio_bytes,
            filename=filename,
            mime=mime,
            duration_s=duration_s,
        )

        if not transcript_text:
            log.warning(
                "transcription.empty_result",
                artifact_id=artifact_id,
                message_id=message_id,
            )
            return False

        if msg.text:
            msg.text = f"{msg.text}\n{transcript_text}"
        else:
            msg.text = transcript_text

        await self.cache.save(message_id, transcript_text, artifact_id)

        if "transcription_metadata" not in msg.metadata:
            msg.metadata["transcription_metadata"] = []
        msg.metadata["transcription_metadata"].append(
            {
                "filename": filename,
                "mime": mime,
                "size_bytes": len(audio_bytes),
                "duration_s": duration_s,
                "artifact_id": artifact_id,
            }
        )

        return True


class FallbackHandler:
    """Handles fallback scenarios when transcription fails."""

    def __init__(self, backend_client: BackendClient | None):
        self.backend_client = backend_client

    async def apply_if_needed(
        self,
        batch: list[IncomingMessage],
        transcription_succeeded: bool,
        had_existing_text: bool,
    ) -> None:
        """Apply fallback text if all transcriptions failed."""
        if transcription_succeeded or had_existing_text or not batch:
            return

        fallback_text = "Извините, не удалось распознать аудио. Пожалуйста, повторите сообщение или отправьте текстом."
        most_recent_msg = batch[-1]
        most_recent_msg.text = fallback_text

        if self.backend_client:
            message_id = most_recent_msg.metadata.get("backend_message_id")
            if message_id:
                try:
                    await self.backend_client.save_transcription(message_id, fallback_text)
                    log.info(
                        "transcription.fallback_saved_to_backend",
                        message_id=message_id,
                    )
                except Exception as e:
                    log.warning(
                        "transcription.fallback_save_failed",
                        message_id=message_id,
                        error=str(e),
                    )
            else:
                log.warning(
                    "transcription.fallback_message_id_not_found",
                    metadata_keys=list(most_recent_msg.metadata.keys()),
                )

        log.info(
            "transcription.all_failed_fallback",
            batch_size=len(batch),
        )


async def transcribe_if_audio(
    batch: list[IncomingMessage],
    settings: SalesAgentSettings,
    backend_client: BackendClient | None = None,
) -> None:
    """Pre-process audio attachments: transcribe and attach text to messages.

    Checks transcription cache in Backend first. If cached, uses cached text.
    Otherwise, downloads file from Backend S3, transcribes, and saves to Backend.

    On success, writes transcript back into msg.text (appends if text already present).
    Does not throw on failure; logs and continues.

    Args:
        batch: List of incoming messages that may contain audio attachments
        settings: Application settings with audio transcription config
        backend_client: Backend client for cache check, transcription save, and artifact download (optional)
    """
    audio_config = settings.audio

    collector = AudioAttachmentCollector()
    audio_attachments = collector.collect(batch)

    if not audio_attachments:
        return

    log.info(
        "transcription.batch_started",
        batch_size=len(batch),
        audio_count=len(audio_attachments),
    )

    service = OpenAITranscriptionService(settings)
    cache = TranscriptionCache(backend_client)
    downloader = AudioFileDownloader(backend_client, audio_config)
    processor = TranscriptionProcessor(service, cache, downloader, audio_config)
    fallback_handler = FallbackHandler(backend_client)

    transcription_succeeded = False
    had_existing_text = any(msg.text and msg.text.strip() for msg in batch)

    for msg, att in audio_attachments:
        try:
            success = await processor.process(msg, att)
            if success:
                transcription_succeeded = True
        except TranscriptionError as e:
            log.warning(
                "transcription.message_failed",
                artifact_id=att.get("artifact_id", "unknown"),
                mime=att.get("mime"),
                error=str(e),
            )
        except Exception as e:
            log.exception(
                "transcription.unexpected_error",
                artifact_id=att.get("artifact_id", "unknown"),
                mime=att.get("mime"),
                error=str(e),
            )

    await fallback_handler.apply_if_needed(batch, transcription_succeeded, had_existing_text)

    log.info(
        "transcription.batch_completed",
        processed=len(audio_attachments),
        succeeded=transcription_succeeded,
    )


def _should_transcode(mime: str | None, filename: str | None) -> bool:
    name = (filename or "").lower()
    if mime in {"audio/ogg", "audio/opus"}:
        return True
    if name.endswith((".ogg", ".opus")):
        return True
    return False


async def _transcode_to_wav(audio_bytes: bytes, *, ffmpeg_path: str = "ffmpeg", timeout_s: float = 60.0) -> bytes:
    """Transcode input bytes to WAV 16k mono using ffmpeg.

    Raises RuntimeError on non-zero return code or timeout.
    """
    proc = await asyncio.create_subprocess_exec(
        ffmpeg_path,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        out, err = await asyncio.wait_for(proc.communicate(input=audio_bytes), timeout=timeout_s)
    except TimeoutError as exc:
        try:
            proc.kill()
        except Exception:
            pass
        raise RuntimeError("ffmpeg transcode timeout") from exc

    if proc.returncode != 0:
        raise RuntimeError((err or b"").decode("utf-8", errors="ignore"))

    return out
