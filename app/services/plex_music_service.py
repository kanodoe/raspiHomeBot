import httpx
import hashlib
import re
import os
from typing import Dict, Any, Optional
from app.core.config import settings
from app.core.logging import logger
from app.utils.ssh import run_ssh_command

class PlexMusicService:
    @classmethod
    async def process_generated_song(cls, task_id: str, audio_path_on_remote: str, metadata: Dict[str, Any], user_info: Dict[str, Any], language: Optional[str] = None):
        """
        Processes a generated song for Plex:
        1. Copies it to the Plex music folder on the remote machine.
        2. Updates ID3 tags (Title, Artist, Album Artist/Author).
        3. Notifies Plex to scan for new files.
        """
        if not settings.PLEX_URL or not settings.PLEX_TOKEN:
            logger.warning("Plex URL or Token not configured, skipping Plex processing.")
            return

        # 1. Prepare Metadata
        prompt = user_info.get("prompt", "")
        # Extract BPM from prompt (e.g., "120 BPM" or "120BPM")
        bpm_match = re.search(r"(\d+)\s*BPM", prompt, re.IGNORECASE)
        bpm = bpm_match.group(1) if bpm_match else "N/A"
        
        # Clean style (take first few tags or first part of prompt)
        style = prompt.split(",")[0].strip() if "," in prompt else prompt.strip()
        style = style[:30] # Limit length
        
        lang = language or "Unknown"
        
        # Generate hash
        hash_str = hashlib.md5(f"{task_id}{prompt}".encode()).hexdigest()[:8]
        
        # New filename/title: Style - BPM - Lang [hash]
        new_title = f"{style} - {bpm} BPM - {lang} [{hash_str}]"
        author = user_info.get("display_name") or user_info.get("username") or "Unknown"
        artist = "RaspiValSong"

        # Sanitize for PowerShell and ffmpeg
        def ps_escape(s: str) -> str:
            if not s: return ""
            # In PowerShell double quoted strings, we escape double quotes with `
            # But here we are passing the whole script as a string to powershell -Command "..."
            # which is even more complex.
            # A safer way is to replace double quotes with single quotes or just remove them for the filename.
            return s.replace('"', "'")

        safe_new_title = ps_escape(new_title)
        safe_author = ps_escape(author)
        safe_artist = ps_escape(artist)

        # 2. Remote Copy and Tagging via SSH
        # Since we are on Windows, we'll try to use ffmpeg if available or just copy.
        # We assume ffmpeg is in the PATH or we use a powershell command that might work for some properties.

        remote_dest_dir = settings.PLEX_REMOTE_MUSIC_PATH
        new_filename = f"{new_title}.mp3".replace("/", "-").replace("\\", "-").replace(":", "-").replace('"', "")
        remote_dest_path = f"{remote_dest_dir}\\{new_filename}"

        logger.info(f"PlexMusicService: Processing song {task_id} for user {author}")

        # We'll use a PowerShell script that:
        # 1. Ensures the destination directory exists.
        # 2. Copies the file.
        # 3. Tries to use ffmpeg to set metadata (if available).

        # Using single quotes for PowerShell variables to avoid most injection/breakage issues
        ps_script = f"""
$destDir = @'
{remote_dest_dir}
'@
if (!(Test-Path $destDir)) {{ New-Item -ItemType Directory -Force -Path $destDir }}

$src = @'
{audio_path_on_remote}
'@
$dest = @'
{remote_dest_path}
'@

Copy-Item -Path $src -Destination $dest -Force

# Try to use ffmpeg for metadata
$tempDest = "$dest.tmp.mp3"
try {{
    ffmpeg -i $dest -metadata title="{safe_new_title}" -metadata artist="{safe_artist}" -metadata album_artist="{safe_artist}" -metadata composer="{safe_author}" -c copy $tempDest -y -loglevel error
    if ($LASTEXITCODE -eq 0) {{
        Move-Item -Path $tempDest -Destination $dest -Force
        Write-Host "Metadata updated with ffmpeg"
    }} else {{
        if (Test-Path $tempDest) {{ Remove-Item $tempDest }}
        Write-Host "ffmpeg failed with exit code $LASTEXITCODE"
    }}
}} catch {{
    Write-Host "ffmpeg not found or failed"
}}
"""
        
        # Prepare the final command for SSH. 
        # We use single quotes for the outer powershell -Command to avoid shell expansion of $
        # But wait, run_ssh_command just passes the string to asyncssh.
        # PowerShell -EncodedCommand is the most robust way but harder to debug here.
        # Let's use a simpler approach: base64 encode the script and run it.
        import base64
        encoded_ps = base64.b64encode(ps_script.encode('utf-16-le')).decode('ascii')
        full_command = f"powershell -EncodedCommand {encoded_ps}"

        ssh_host = settings.ACESTEP_HOST
        if ssh_host in ("localhost", "127.0.0.1", "0.0.0.0"):
            ssh_host = settings.PC_IP
            
        success = await run_ssh_command(full_command, ssh_host)
        
        if success:
            logger.info(f"PlexMusicService: Song copied and tagged at {remote_dest_path}")
            # 3. Notify Plex
            await cls.notify_plex_scan()
        else:
            logger.error(f"PlexMusicService: Failed to copy/tag song {task_id}")

    @classmethod
    async def notify_plex_scan(cls):
        """
        Sends a refresh request to Plex.
        """
        if not settings.PLEX_URL or not settings.PLEX_TOKEN:
            return

        section_id = settings.PLEX_MUSIC_SECTION_ID
        if not section_id:
            logger.warning("PLEX_MUSIC_SECTION_ID not configured, cannot trigger targeted scan. Triggering global scan?")
            # We could trigger a global scan, but let's just warn for now.
            return

        url = f"{settings.PLEX_URL}/library/sections/{section_id}/refresh"
        params = {"X-Plex-Token": settings.PLEX_TOKEN}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=10.0)
                if response.status_code in (200, 201):
                    logger.info(f"Plex scan triggered for section {section_id}")
                else:
                    logger.error(f"Plex refresh failed: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Error notifying Plex: {e}")
