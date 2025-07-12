# downloader.py
import os
import asyncio
import subprocess


def get_filesize_mb(file_path):
    try:
        return round(os.path.getsize(file_path) / (1024 * 1024), 2)
    except:
        return 0


async def download_m3u8_ffmpeg(m3u8_url, output_path, progress_msg, client):
    try:
        command = [
            "ffmpeg", "-y", "-i", m3u8_url,
            "-movflags", "+faststart",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
            "-c:a", "aac", "-b:a", "128k",
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        last_percent = 0
        while True:
            await asyncio.sleep(2)
            if os.path.exists(output_path):
                size_mb = get_filesize_mb(output_path)
                percent = min(int(size_mb / 1024 * 100), 100)
                if percent >= last_percent + 1:
                    await progress_msg.edit(f"⬇️ Downloading... {percent}%")
                    last_percent = percent

            if process.returncode is not None:
                break

            await process.wait()

        return os.path.exists(output_path) and os.path.getsize(output_path) > 0

    except Exception as e:
        await progress_msg.edit(f"❌ FFmpeg error: {str(e)}")
        return False


async def download_with_ytdlp(m3u8_url, output_path, progress_msg, client):
    try:
        command = [
            "yt-dlp", m3u8_url,
            "-o", output_path,
            "--no-playlist",
            "--hls-prefer-ffmpeg",
            "--no-part"
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        last_percent = 0
        while True:
            await asyncio.sleep(2)
            if os.path.exists(output_path):
                size_mb = get_filesize_mb(output_path)
                percent = min(int(size_mb / 1024 * 100), 100)
                if percent >= last_percent + 1:
                    await progress_msg.edit(f"⬇️ Downloading... {percent}%")
                    last_percent = percent

            if process.returncode is not None:
                break

            await process.wait()

        return os.path.exists(output_path) and os.path.getsize(output_path) > 0

    except Exception as e:
        await progress_msg.edit(f"❌ yt-dlp error: {str(e)}")
        return False
