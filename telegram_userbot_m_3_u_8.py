# bot.py
import asyncio
import logging
import os
import re
import time
import shutil
from urllib.parse import urlparse, parse_qs
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession

from downloader import download_m3u8_ffmpeg, download_with_ytdlp, get_filesize_mb
from queue_manager import queue_handler, set_owner, is_owner, user_on_cooldown, block_user_temporarily, cancel_task
from config import API_ID, API_HASH, SESSION_STRING, OWNER_PASSWORD

logging.basicConfig(level=logging.INFO)

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
task_queue = asyncio.Queue()
running_tasks = {}
user_states = {}  # Maps user_id -> {'downloading': bool, 'cooldown_until': timestamp}

MAX_CONCURRENT_DOWNLOADS = 4
MAX_FILE_SIZE_MB = 1024
COOLDOWN_SECONDS = 600
TEMP_BLOCK_SECONDS = 1200

VALID_DOMAIN = 'cloudfront.net'
VALID_SUFFIX = '.m3u8'


# --- Utility Functions ---
def extract_m3u8_link(study_url):
    try:
        if not study_url.startswith("https://studysmarterx.netlify.app/Player?url="):
            return None
        parsed = urlparse(study_url)
        real_url = parse_qs(parsed.query).get("url", [None])[0]
        if real_url and VALID_DOMAIN in real_url and real_url.endswith(VALID_SUFFIX):
            return real_url
        return None
    except:
        return None


# --- Main Commands ---
@client.on(events.NewMessage(pattern=r"/owner"))
async def owner_auth(event):
    await event.respond("🔒 Enter owner password:")

    response = await client.wait_for(events.NewMessage(from_users=event.sender_id))
    if response.raw_text.strip() == OWNER_PASSWORD:
        set_owner(event.sender_id)
        await response.reply("✅ Owner access granted! You are now exempt from limits.")
    else:
        await response.reply("❌ Incorrect password.")


@client.on(events.NewMessage(pattern=r"/(live|recorded) (.+)"))
async def process_download(event):
    cmd, link = event.pattern_match.groups()
    user_id = event.sender_id

    real_url = extract_m3u8_link(link.strip())
    if not real_url:
        await event.reply("❌ Invalid link. Must be StudySmarter CloudFront .m3u8 URL.")
        return

    # Quality selection
    buttons = [
        [Button.inline("240p", f"q|{cmd}|{real_url}|1")],
        [Button.inline("360p", f"q|{cmd}|{real_url}|2")],
        [Button.inline("480p", f"q|{cmd}|{real_url}|3")],
        [Button.inline("720p", f"q|{cmd}|{real_url}|4")],
        [Button.inline("❌ Cancel", b"cancel")]
    ]
    await event.reply("🎥 Select video quality:", buttons=buttons)


@client.on(events.CallbackQuery(pattern=b"q\|(live|recorded)\|(.+)\|(\d+)"))
async def handle_quality_selection(event):
    await event.answer()
    cmd, real_url, index = event.pattern_match.groups()
    user_id = event.sender_id
    quality_url = re.sub(r"index_\d", f"index_{index}", real_url)

    if not is_owner(user_id):
        if user_id in user_states and user_states[user_id].get("downloading"):
            await event.respond("⚠️ You already have an active download. Wait until it finishes.")
            return
        if user_on_cooldown(user_id):
            await event.respond("🕒 You are on cooldown. Try again later.")
            return

    await event.respond("📝 Send an optional caption or type /skip to continue without one:")
    reply = await client.wait_for(events.NewMessage(from_users=user_id))
    caption = reply.raw_text if not reply.raw_text.startswith("/skip") else ""
    caption += "\n\nDownloaded via @studysmarterhub bot"

    task_data = {
        'user_id': user_id,
        'url': quality_url,
        'cmd': cmd,
        'caption': caption,
        'chat_id': event.chat_id,
        'reply_to': event.id
    }

    await queue_handler(task_queue, running_tasks, user_states, event, task_data, client)


@client.on(events.NewMessage(pattern=r"/cancel"))
async def cancel_download(event):
    user_id = event.sender_id
    cancelled = cancel_task(user_id, task_queue, running_tasks)
    if cancelled:
        await event.reply("❌ Your current/queued download was cancelled.")
    else:
        await event.reply("ℹ️ No active or queued download found to cancel.")


@client.on(events.CallbackQuery(pattern=b"cancel"))
async def cancel_button(event):
    user_id = event.sender_id
    cancelled = cancel_task(user_id, task_queue, running_tasks)
    await event.answer("Cancelled.", alert=True)
    if cancelled:
        await event.edit("❌ Your current/queued download was cancelled.")
    else:
        await event.edit("ℹ️ No active or queued download found to cancel.")


async def worker():
    while True:
        if len(running_tasks) >= MAX_CONCURRENT_DOWNLOADS:
            await asyncio.sleep(2)
            continue

        task = await task_queue.get()
        user_id = task['user_id']
        user_states[user_id] = {"downloading": True}

        progress_msg = await client.send_message(task['chat_id'], "⬇️ Starting download...", reply_to=task['reply_to'])
        file_path = f"video_{user_id}_{int(time.time())}.mp4"

        try:
            if task['cmd'] == 'live':
                success = await download_m3u8_ffmpeg(task['url'], file_path, progress_msg, client)
            else:
                success = await download_with_ytdlp(task['url'], file_path, progress_msg, client)

            if not success:
                await progress_msg.edit("❌ Download failed.")
                continue

            size_mb = get_filesize_mb(file_path)
            if size_mb > MAX_FILE_SIZE_MB:
                await progress_msg.edit("❌ File exceeds 1GB. You are blocked for 20 minutes.")
                block_user_temporarily(user_id, TEMP_BLOCK_SECONDS)
                try:
                    os.remove(file_path)
                except:
                    pass
                continue

            final_path = "Downloaded via @studysmarterhub.mp4"
            shutil.move(file_path, final_path)
            await client.send_file(task['chat_id'], final_path, caption=task['caption'])
            await progress_msg.edit("✅ Upload complete!")
            try:
                os.remove(final_path)
            except:
                pass

        except Exception as e:
            await progress_msg.edit(f"❌ Error: {str(e)}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass

        finally:
            user_states[user_id] = {"downloading": False, "cooldown_until": time.time() + COOLDOWN_SECONDS}
            running_tasks.pop(user_id, None)


