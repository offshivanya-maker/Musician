import asyncio
import logging
import subprocess
from typing import Optional, Dict, Any
import os

logger = logging.getLogger(__name__)


class FFmpegManager:
    """Manages FFmpeg processes for streaming"""
    
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
        self.process: Optional[asyncio.subprocess.Process] = None
    
    async def check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available"""
        try:
            process = await asyncio.create_subprocess_exec(
                self.ffmpeg_path, "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.wait()
            return process.returncode == 0
        except Exception as e:
            logger.error(f"FFmpeg check failed: {e}")
            return False
    
    async def prepare_stream_input(self, media_path: str, input_format: str = "file") -> Dict[str, Any]:
        """Prepare input for FFmpeg stream"""
        
        # Get media info
        cmd = [
            self.ffmpeg_path,
            "-i", media_path,
            "-f", "null",
            "-"
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            
            # Parse FFmpeg output for media info
            info = self._parse_ffmpeg_info(stderr.decode())
            return {
                "path": media_path,
                "format": input_format,
                "info": info,
                "duration": info.get("duration"),
                "is_video": info.get("has_video", False),
                "is_audio": info.get("has_audio", False),
            }
        except Exception as e:
            logger.error(f"Failed to get media info: {e}")
            return {"path": media_path, "format": input_format}
    
    def _parse_ffmpeg_info(self, output: str) -> Dict[str, Any]:
        """Parse FFmpeg output for media information"""
        info = {
            "has_video": False,
            "has_audio": False,
            "duration": None,
            "codec": None,
        }
        
        lines = output.split("\n")
        for line in lines:
            if "Video:" in line:
                info["has_video"] = True
            if "Audio:" in line:
                info["has_audio"] = True
            if "Duration:" in line:
                # Extract duration in seconds
                import re
                match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d+)", line)
                if match:
                    h, m, s = match.groups()
                    info["duration"] = int(h) * 3600 + int(m) * 60 + float(s)
        
        return info
    
    async def get_stream_command(
        self,
        media_path: str,
        is_video: bool = False,
        audio_bitrate: str = "64k",
        video_bitrate: str = "500k",
        frame_size: str = "720x480"
    ) -> list:
        """Build FFmpeg command for streaming"""
        
        cmd = [self.ffmpeg_path]
        
        # Input
        cmd.extend(["-i", media_path])
        
        # Video settings if applicable
        if is_video:
            # Transcode video to compatible format
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "fast",
                "-b:v", video_bitrate,
                "-s", frame_size,
                "-r", "30",
                "-c:a", "aac",
                "-b:a", audio_bitrate,
                "-ar", "44100",
                "-ac", "2",
            ])
        else:
            # Audio only
            cmd.extend([
                "-vn",
                "-c:a", "aac",
                "-b:a", audio_bitrate,
                "-ar", "44100",
                "-ac", "2",
            ])
        
        # Output format for Telegram voice chat
        cmd.extend([
            "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov",
            "pipe:1"
        ])
        
        return cmd
    
    async def kill_process(self):
        """Kill the FFmpeg process if running"""
        if self.process and self.process.returncode is None:
            try:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
            except Exception as e:
                logger.error(f"Error killing FFmpeg process: {e}")
            finally:
                self.process = None
