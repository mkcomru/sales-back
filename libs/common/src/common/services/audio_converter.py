"""Audio conversion service using ffmpeg."""

from __future__ import annotations

import asyncio
import shutil

import ffmpeg
import structlog

log = structlog.get_logger(__name__)


class AudioConversionError(Exception):
    """Raised when audio conversion fails."""


def _resolve_ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise AudioConversionError("ffmpeg binary not found on PATH")
    return path


class AudioConversionService:
    """Service for converting audio files to MP3 format using ffmpeg."""

    def __init__(self) -> None:
        self._ffmpeg_cmd = _resolve_ffmpeg_path()
        log.info("audio_converter.init", ffmpeg_path=self._ffmpeg_cmd)

    async def convert_to_mp3(
        self,
        audio_bytes: bytes,
        input_format: str | None = None,
        timeout_s: float = 60.0,
    ) -> bytes:
        """Convert audio bytes to MP3 format.

        Args:
            audio_bytes: Input audio file bytes
            input_format: Optional input format hint (e.g., "ogg", "opus", "wav")
            timeout_s: Conversion timeout in seconds (default: 60.0)

        Returns:
            Converted audio bytes in MP3 format

        Raises:
            AudioConversionError: If conversion fails or times out
        """
        log.info(
            "audio_conversion.started",
            input_size_bytes=len(audio_bytes),
            input_format=input_format,
            timeout_s=timeout_s,
        )

        def _convert(audio: bytes) -> bytes:
            """Synchronous conversion function."""
            try:
                input_kwargs = {}
                if input_format:
                    input_kwargs["format"] = input_format

                out, _ = (
                    ffmpeg.input("pipe:0", **input_kwargs)
                    .output(
                        "pipe:1",
                        format="mp3",
                        acodec="libmp3lame",
                        audio_bitrate="128k",
                    )
                    .run(cmd=self._ffmpeg_cmd, input=audio, capture_stdout=True, capture_stderr=True, quiet=True)
                )
                return out
            except ffmpeg.Error as e:
                error_output = (e.stderr or b"").decode("utf-8", errors="ignore")
                error_msg = f"ffmpeg conversion failed: {error_output}"
                log.error(
                    "audio_conversion.failed",
                    error_output=error_output,
                )
                raise AudioConversionError(error_msg) from e
            except Exception as e:
                error_msg = f"Audio conversion failed: {e}"
                log.error(
                    "audio_conversion.unexpected_error",
                    error=str(e),
                )
                raise AudioConversionError(error_msg) from e

        try:
            out = await asyncio.wait_for(asyncio.to_thread(_convert, audio_bytes), timeout=timeout_s)
        except TimeoutError as e:
            error_msg = f"Audio conversion timeout after {timeout_s}s"
            log.error("audio_conversion.timeout", timeout_s=timeout_s)
            raise AudioConversionError(error_msg) from e

        log.info(
            "audio_conversion.completed",
            input_size_bytes=len(audio_bytes),
            output_size_bytes=len(out),
        )

        return out
