"""Tests for AudioConversionService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import ffmpeg
import pytest

from common.services.audio_converter import AudioConversionError, AudioConversionService


class TestAudioConversionService:
    """Tests for AudioConversionService."""

    @pytest.mark.asyncio
    async def test_convert_to_mp3_success(self) -> None:
        """Test successful audio conversion to MP3."""
        service = AudioConversionService()

        input_bytes = b"fake audio input"
        output_bytes = b"fake mp3 output"

        mock_input = MagicMock()
        mock_output = MagicMock()
        mock_input.output.return_value = mock_output
        mock_output.run.return_value = (output_bytes, b"")

        async def mock_to_thread(func, *args):
            return func(*args)

        with (
            patch("common.services.audio_converter.ffmpeg.input", return_value=mock_input),
            patch("asyncio.to_thread", side_effect=mock_to_thread),
        ):
            result = await service.convert_to_mp3(input_bytes, input_format="ogg")

            assert result == output_bytes
            mock_input.output.assert_called_once()
            mock_output.run.assert_called_once_with(
                input=input_bytes,
                capture_stdout=True,
                capture_stderr=True,
                quiet=True,
            )

    @pytest.mark.asyncio
    async def test_convert_to_mp3_without_format(self) -> None:
        """Test audio conversion without specifying input format."""
        service = AudioConversionService()

        input_bytes = b"fake audio input"
        output_bytes = b"fake mp3 output"

        mock_input = MagicMock()
        mock_output = MagicMock()
        mock_input.output.return_value = mock_output
        mock_output.run.return_value = (output_bytes, b"")

        async def mock_to_thread(func, *args):
            return func(*args)

        with (
            patch("common.services.audio_converter.ffmpeg.input", return_value=mock_input) as mock_ffmpeg_input,
            patch("asyncio.to_thread", side_effect=mock_to_thread),
        ):
            result = await service.convert_to_mp3(input_bytes, input_format=None)

            assert result == output_bytes
            mock_ffmpeg_input.assert_called_once_with("pipe:0")
            mock_output.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_convert_to_mp3_custom_timeout(self) -> None:
        """Test audio conversion with custom timeout."""
        service = AudioConversionService()

        input_bytes = b"fake audio input"
        output_bytes = b"fake mp3 output"

        mock_input = MagicMock()
        mock_output = MagicMock()
        mock_input.output.return_value = mock_output
        mock_output.run.return_value = (output_bytes, b"")

        with (
            patch("common.services.audio_converter.ffmpeg.input", return_value=mock_input),
            patch("asyncio.wait_for") as mock_wait_for,
        ):
            mock_wait_for.return_value = output_bytes

            result = await service.convert_to_mp3(input_bytes, timeout_s=120.0)

            assert result == output_bytes
            mock_wait_for.assert_called_once()
            assert mock_wait_for.call_args[1]["timeout"] == 120.0

    @pytest.mark.asyncio
    async def test_convert_to_mp3_ffmpeg_error(self) -> None:
        """Test conversion when ffmpeg raises Error."""
        service = AudioConversionService()

        input_bytes = b"fake audio input"
        error_stderr = b"Error: Invalid input format"

        mock_input = MagicMock()
        mock_output = MagicMock()
        mock_input.output.return_value = mock_output

        error = ffmpeg.Error("ffmpeg", b"", error_stderr)
        mock_output.run.side_effect = error

        with patch("common.services.audio_converter.ffmpeg.input", return_value=mock_input):
            with pytest.raises(AudioConversionError, match="ffmpeg conversion failed"):
                await service.convert_to_mp3(input_bytes)

    @pytest.mark.asyncio
    async def test_convert_to_mp3_timeout(self) -> None:
        """Test conversion timeout handling."""
        service = AudioConversionService()

        input_bytes = b"fake audio input"

        with patch("asyncio.wait_for") as mock_wait_for:
            mock_wait_for.side_effect = TimeoutError("Operation timed out")

            with pytest.raises(AudioConversionError, match="timeout"):
                await service.convert_to_mp3(input_bytes, timeout_s=1.0)

            mock_wait_for.assert_called_once()

    @pytest.mark.asyncio
    async def test_convert_to_mp3_unexpected_error(self) -> None:
        """Test conversion when unexpected exception occurs."""
        service = AudioConversionService()

        input_bytes = b"fake audio input"

        mock_input = MagicMock()
        mock_output = MagicMock()
        mock_input.output.return_value = mock_output
        mock_output.run.side_effect = ValueError("Unexpected error")

        with patch("common.services.audio_converter.ffmpeg.input", return_value=mock_input):
            with pytest.raises(AudioConversionError, match="Audio conversion failed"):
                await service.convert_to_mp3(input_bytes)

    @pytest.mark.asyncio
    async def test_convert_to_mp3_different_formats(self) -> None:
        """Test conversion with different input formats."""
        service = AudioConversionService()

        input_bytes = b"fake audio input"
        output_bytes = b"fake mp3 output"

        formats = ["ogg", "opus", "wav", "m4a", "aac"]

        async def mock_to_thread(func, *args):
            return func(*args)

        for input_format in formats:
            mock_input = MagicMock()
            mock_output = MagicMock()
            mock_input.output.return_value = mock_output
            mock_output.run.return_value = (output_bytes, b"")

            with (
                patch("common.services.audio_converter.ffmpeg.input", return_value=mock_input) as mock_ffmpeg_input,
                patch("asyncio.to_thread", side_effect=mock_to_thread),
            ):
                result = await service.convert_to_mp3(input_bytes, input_format=input_format)

                assert result == output_bytes
                mock_ffmpeg_input.assert_called_once_with("pipe:0", format=input_format)

    @pytest.mark.asyncio
    async def test_convert_to_mp3_empty_input(self) -> None:
        """Test conversion with empty input."""
        service = AudioConversionService()

        input_bytes = b""
        output_bytes = b""

        mock_input = MagicMock()
        mock_output = MagicMock()
        mock_input.output.return_value = mock_output
        mock_output.run.return_value = (output_bytes, b"")

        with patch("common.services.audio_converter.ffmpeg.input", return_value=mock_input):
            result = await service.convert_to_mp3(input_bytes)

            assert result == output_bytes

    @pytest.mark.asyncio
    async def test_convert_to_mp3_large_input(self) -> None:
        """Test conversion with large input."""
        service = AudioConversionService()

        input_bytes = b"x" * (10 * 1024 * 1024)  # 10MB
        output_bytes = b"y" * (5 * 1024 * 1024)  # 5MB

        mock_input = MagicMock()
        mock_output = MagicMock()
        mock_input.output.return_value = mock_output
        mock_output.run.return_value = (output_bytes, b"")

        with patch("common.services.audio_converter.ffmpeg.input", return_value=mock_input):
            result = await service.convert_to_mp3(input_bytes)

            assert result == output_bytes
            assert len(result) < len(input_bytes)

    @pytest.mark.asyncio
    async def test_convert_to_mp3_ffmpeg_args_structure(self) -> None:
        """Test that ffmpeg arguments are correctly structured."""
        service = AudioConversionService()

        input_bytes = b"fake audio input"
        output_bytes = b"fake mp3 output"

        mock_input = MagicMock()
        mock_output = MagicMock()
        mock_input.output.return_value = mock_output
        mock_output.run.return_value = (output_bytes, b"")

        async def mock_to_thread(func, *args):
            return func(*args)

        with (
            patch("common.services.audio_converter.ffmpeg.input", return_value=mock_input) as mock_ffmpeg_input,
            patch("asyncio.to_thread", side_effect=mock_to_thread),
        ):
            await service.convert_to_mp3(input_bytes, input_format="ogg")

            mock_ffmpeg_input.assert_called_once_with("pipe:0", format="ogg")
            mock_input.output.assert_called_once_with(
                "pipe:1",
                format="mp3",
                acodec="libmp3lame",
                audio_bitrate="128k",
            )
            mock_output.run.assert_called_once_with(
                input=input_bytes,
                capture_stdout=True,
                capture_stderr=True,
                quiet=True,
            )
