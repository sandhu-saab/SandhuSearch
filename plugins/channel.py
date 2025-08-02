import re
import io
import math
import random
import string
import aiohttp
import asyncio
import hashlib
from datetime import datetime
from typing import Optional, Dict
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified

from info import *
from utils import *
from database.ia_filterdb import save_file

# ✅ Languages list for caption parsing
CAPTION_LANGUAGES = ["Bhojpuri", "Hindi", "Bengali", "Tamil", "English", "Bangla", "Telugu", "Malayalam", "Kannada", "Marathi", "Punjabi", "Gujrati", "Korean", "Gujarati", "Spanish", "French", "German", "Chinese", "Arabic", "Portuguese", "Russian", "Japanese", "Odia", "Assamese", "Urdu"]

# ✅ Update caption format
UPDATE_CAPTION = """<b>【{TITLE} ({YEAR})】🆕️

📺 Format - {FORMATS}
🔰 Quality - {QUALITIES}
🔈 Audio - {LANGUAGES}
🎭 Genres - {GENRES}
⭐️ Rating - {RATING}★
📡 OTT - {OTT}

👑 Provided By : {PROVIDER}</b>
"""

# ✅ Global dicts for movie tracking & reactions
movie_data: Dict[str, Dict] = {}
reaction_counts: Dict[str, Dict] = {}
user_reactions: Dict[str, Dict] = {}

media_filter = filters.document | filters.video | filters.audio

@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    """Handles new media messages"""
    media = next((getattr(message, attr) for attr in ("document", "video", "audio") if getattr(message, attr, None)), None)
    if not media:
        return

    media.file_type = media.mime_type
    media.caption = message.caption

    success, silentxbotz = await save_file(bot, media)
    try:
        if success and silentxbotz == 1:
            await send_movie_update(bot, file_name=media.file_name, caption=media.caption)
    except Exception as e:
        print(f"Error in media handler: {e}")


async def send_movie_update(bot, file_name, caption):
    try:
        clean_name = await movie_name_format(file_name)
        year_match = re.search(r"\b(19|20)\d{2}\b", caption)
        year = year_match.group(0) if year_match else None
        search_query = clean_name.replace(" ", "-")

        # ✅ Create movie_id (hash)
        movie_id = hashlib.md5(clean_name.encode()).hexdigest()[:8]

        # ✅ Extract quality, format, language, ott
        quality = await get_pixels(caption) or "Unknown"
        fmt = await get_qualities(caption) or "ORG"
        language = ", ".join([lang for lang in CAPTION_LANGUAGES if lang.lower() in caption.lower()]) or "Unknown"
        ott_match = re.search(r"(Netflix|Amazon Prime|Disney\+ Hotstar|SonyLiv|ZEE5|JioCinema|Apple TV\+)", caption, re.I)
        ott = ott_match.group(0) if ott_match else None

        # ✅ Initialize if movie not exists
        if movie_id not in movie_data:
            imdb_data = await get_imdb_details(clean_name)
            poster = await fetch_movie_poster(imdb_data.get("title", clean_name), year)
            genres = ", ".join(imdb_data.get("genres", [])) or "N/A"
            rating = imdb_data.get("rating", "N/A")

            movie_data[movie_id] = {
                'title': imdb_data.get("title", clean_name),
                'year': year or "N/A",
                'formats': set(),
                'qualities': set(),
                'languages': set(),
                'ott': set(),
                'message_id': None,
                'poster': poster,
                'genres': genres,
                'rating': rating
            }
            reaction_counts[movie_id] = {"❤️": 0, "👍": 0, "👎": 0, "🔥": 0}
            user_reactions[movie_id] = {}

        # ✅ Add details to sets
        movie_data[movie_id]['formats'].add(fmt)
        movie_data[movie_id]['qualities'].add(quality)
        movie_data[movie_id]['languages'].add(language)
        if ott:
            movie_data[movie_id]['ott'].add(ott)

        # ✅ Prepare caption
        full_caption = UPDATE_CAPTION.format(
            TITLE=movie_data[movie_id]['title'],
            YEAR=movie_data[movie_id]['year'],
            FORMATS=", ".join(sorted(movie_data[movie_id]['formats'])),
            QUALITIES=", ".join(sorted(movie_data[movie_id]['qualities'])),
            LANGUAGES=", ".join(sorted(movie_data[movie_id]['languages'])),
            GENRES=movie_data[movie_id]['genres'],
            RATING=movie_data[movie_id]['rating'],
            OTT=", ".join(sorted(movie_data[movie_id]['ott'])) if movie_data[movie_id]['ott'] else "N/A",
            PROVIDER=PROVIDER_NAME
        )

        # ✅ Buttons
        buttons = [[
            InlineKeyboardButton(f"❤️ {reaction_counts[movie_id]['❤️']}", callback_data=f"r_{movie_id}_{search_query}_heart"),
            InlineKeyboardButton(f"👍 {reaction_counts[movie_id]['👍']}", callback_data=f"r_{movie_id}_{search_query}_like"),
            InlineKeyboardButton(f"👎 {reaction_counts[movie_id]['👎']}", callback_data=f"r_{movie_id}_{search_query}_dislike"),
            InlineKeyboardButton(f"🔥 {reaction_counts[movie_id]['🔥']}", callback_data=f"r_{movie_id}_{search_query}_fire")
        ], [
            InlineKeyboardButton('📂 Get File 📂', url=f'https://telegram.me/{U_NAME}?start=getfile-{search_query}')
        ], [
            InlineKeyboardButton('♻️ How To Download ♻️', url=f'https://t.me/+dVRLYHXJztJlMmY9')
        ]]

        # ✅ If old message exists → edit
        if movie_data[movie_id]['message_id']:
            try:
                await bot.edit_message_caption(
                    chat_id=MOVIE_UPDATE_CHANNEL,
                    message_id=movie_data[movie_id]['message_id'],
                    caption=full_caption,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                print(f"✅ Updated: {movie_data[movie_id]['title']}")
                return
            except MessageNotModified:
                return
            except Exception as e:
                print(f"⚠️ Edit failed: {e}")
                movie_data[movie_id]['message_id'] = None

        # ✅ Else send new message
        sent = await bot.send_photo(
            chat_id=MOVIE_UPDATE_CHANNEL,
            photo=movie_data[movie_id]['poster'] or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg",
            caption=full_caption,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        movie_data[movie_id]['message_id'] = sent.message_id
        print(f"📤 New movie: {movie_data[movie_id]['title']}")

    except Exception as e:
        print(f"Error in send_movie_update: {e}")


# ✅ Reaction Handler
@Client.on_callback_query(filters.regex(r"^r_"))
async def reaction_handler(client, query):
    try:
        _, movie_id, search_query, reaction_key = query.data.split("_")
        user_id = query.from_user.id

        emoji_map = {"heart": "❤️", "like": "👍", "dislike": "👎", "fire": "🔥"}
        if reaction_key not in emoji_map or movie_id not in reaction_counts:
            return

        new_emoji = emoji_map[reaction_key]

        if user_id in user_reactions[movie_id]:
            old_emoji = user_reactions[movie_id][user_id]
            if old_emoji == new_emoji:
                return
            else:
                reaction_counts[movie_id][old_emoji] -= 1

        user_reactions[movie_id][user_id] = new_emoji
        reaction_counts[movie_id][new_emoji] += 1

        updated_buttons = [[
            InlineKeyboardButton(f"❤️ {reaction_counts[movie_id]['❤️']}", callback_data=f"r_{movie_id}_{search_query}_heart"),
            InlineKeyboardButton(f"👍 {reaction_counts[movie_id]['👍']}", callback_data=f"r_{movie_id}_{search_query}_like"),
            InlineKeyboardButton(f"👎 {reaction_counts[movie_id]['👎']}", callback_data=f"r_{movie_id}_{search_query}_dislike"),
            InlineKeyboardButton(f"🔥 {reaction_counts[movie_id]['🔥']}", callback_data=f"r_{movie_id}_{search_query}_fire")
        ], [
            InlineKeyboardButton('📂 Get File 📂', url=f'https://telegram.me/{U_NAME}?start=getfile-{search_query}')
        ], [
            InlineKeyboardButton('♻️ How To Download ♻️', url=f'https://t.me/+dVRLYHXJztJlMmY9')
        ]]

        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(updated_buttons))

    except Exception as e:
        print("Reaction error:", e)


# ✅ IMDb & Poster Functions
async def get_imdb_details(name):
    try:
        formatted_name = await movie_name_format(name)
        imdb = await get_poster(formatted_name)
        return imdb or {}
    except Exception as e:
        print(f"IMDB fetch error: {e}")
        return {}


async def fetch_movie_poster(title: str, year: Optional[int] = None) -> Optional[str]:
    base_url = "https://image.silentxbotz.tech/api/v1/poster"
    params = {"title": title.strip()}
    if year:
        params["year"] = str(year)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as response:
                if response.status == 200:
                    return await response.read()
    except Exception as e:
        print(f"Poster fetch error: {e}")
    return None


# ✅ Helper Functions
async def get_qualities(text):
    qualities = ["HDCAM", "HDRip", "BluRay", "WEB-DL", "WEBRip", "HDTC", "DVDscr", "DVDRip", "HDTS", "ORG", "HQ"]
    for q in qualities:
        if q.lower() in text.lower():
            return q
    return "ORG"


async def get_pixels(text):
    return next((p for p in ["480p", "720p", "1080p", "2160p", "4K"] if p.lower() in text.lower()), "Unknown")


async def movie_name_format(file_name):
    return re.sub(r'http\S+|@\w+|#\w+|[\[\]\(\)\{\}\.\-_:;\'!]', ' ', file_name).strip()


def generate_unique_id(name):
    return hashlib.md5(name.encode()).hexdigest()[:5]
