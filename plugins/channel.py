import re
import io
import math
import random
import string
import aiohttp
import asyncio
import hashlib
import requests
from info import *
from utils import *
from typing import Optional
from datetime import datetime
from pyrogram import Client, filters
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery


CAPTION_LANGUAGES = ["Bhojpuri", "Hindi", "Bengali", "Tamil", "English", "Bangla", "Telugu", "Malayalam", "Kannada", "Marathi", "Punjabi", "Bengoli", "Gujrati", "Korean", "Gujarati", "Spanish", "French", "German", "Chinese", "Arabic", "Portuguese", "Russian", "Japanese", "Odia", "Assamese", "Urdu"]

NEW_UPLOAD_CAPTION = """<b>​​​【{NAME}】🆕️

📺 Fᴏʀᴍᴀᴛ: {QUALITY}
🔰 Qᴜᴀʟɪᴛʏ: 720p, 1080p, etc.
🔈 Aᴜᴅɪᴏ: {LANGUAGES}
🎭 Gᴇɴʀᴇꜱ: {GENRE}
⭐️ IMDb: {RATING}★

<blockquote>👑 Pʀᴏᴠɪᴅᴇᴅ Bʏ : @Baii_Ji</blockquote></b>
"""


notified_movies = set()
user_reactions = {}
reaction_counts = {}

media_filter = filters.document | filters.video | filters.audio

@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    """Media Handler"""
    for file_type in ("document", "video", "audio"):
        media = getattr(message, file_type, None)
        if media is not None:
            break
    else:
        return
    media.file_type = file_type
    media.caption = message.caption
    success, silentxbotz = await save_file(bot, media)
    try:  
        if success and silentxbotz == 1:            
            await send_movie_update(bot, file_name=media.file_name, caption=media.caption)
    except Exception as e:
        print(f"Error In Movie Update - {e}")
        pass

async def send_movie_update(bot, file_name, caption):
    try:
        file_name = await movie_name_format(file_name)
        caption = await movie_name_format(caption)
        year_match = re.search(r"\b(19|20)\d{2}\b", caption)
        year = year_match.group(0) if year_match else None      
        season_match = re.search(r"(?i)(?:s|season)0*(\d{1,2})", caption) or re.search(r"(?i)(?:s|season)0*(\d{1,2})", file_name)
        if year:
            file_name = file_name[:file_name.find(year) + 4]
        elif season_match:
            season = season_match.group(1)
            file_name = file_name[:file_name.find(season) + 1]
        quality = await get_qualities(caption) or "HDRip"
        pixel = await get_pixels(caption) or ""
        language = ", ".join([lang for lang in CAPTION_LANGUAGES if lang.lower() in caption.lower()]) or "Not Idea"
        if file_name in notified_movies:
            return 
        notified_movies.add(file_name)
        imdb_data = await get_imdb_details(file_name)
        title = imdb_data.get("title", file_name)
        imdb_link = imdb_data.get("url", "") if imdb_data else ""
        genre = imdb_data.get("genres", "")
        rating = imdb_data.get("rating", '')
        kind = imdb_data.get("kind", "").strip().upper().replace(" ", "_") if imdb_data else ""
        poster = await fetch_movie_poster(title, year)        
        search_movie = file_name.replace(" ", "-")
        unique_id = generate_unique_id(search_movie)
        reaction_counts[unique_id] = {"❤️": 0, "👍": 0, "👎": 0, "🔥": 0}
        user_reactions[unique_id] = {}
        full_caption = NEW_UPLOAD_CAPTION.format(NAME=file_name, KIND=kind, QUALITY=quality, PIXEL=pixel, LANGUAGES=language, GENRE=genre, RATING=rating, IMDB_LINK=imdb_link)
        buttons = [[
            InlineKeyboardButton(f"❤️ {reaction_counts[unique_id]['❤️']}", callback_data=f"r_{unique_id}_{search_movie}_heart"),                
            InlineKeyboardButton(f"👍 {reaction_counts[unique_id]['👍']}", callback_data=f"r_{unique_id}_{search_movie}_like"),
            InlineKeyboardButton(f"👎 {reaction_counts[unique_id]['👎']}", callback_data=f"r_{unique_id}_{search_movie}_dislike"),
            InlineKeyboardButton(f"🔥 {reaction_counts[unique_id]['🔥']}", callback_data=f"r_{unique_id}_{search_movie}_fire")
        ],[
            InlineKeyboardButton('📂 Gᴇᴛ Fɪʟᴇ 📂', url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{search_movie}')
        ],[
            InlineKeyboardButton('♻️ Hᴏᴡ Tᴏ Dᴏᴡɴʟᴏᴀᴅ ♻️', url=f'https://t.me/+dVRLYHXJztJlMmY9')
        ]]
        if poster:
            photo_file = io.BytesIO(poster)
            photo_file.name = await generate_random_filename()
            await bot.send_photo(chat_id=MOVIE_UPDATE_CHANNEL, photo=photo_file, caption=full_caption, reply_markup=InlineKeyboardMarkup(buttons))    
        else:
            image_url = "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"   
            await bot.send_photo(chat_id=MOVIE_UPDATE_CHANNEL, photo=image_url, caption=full_caption, reply_markup=InlineKeyboardMarkup(buttons))                
    except Exception as e:
        print(f"Error in send_movie_update: {e}")

@Client.on_callback_query(filters.regex(r"^r_"))
async def reaction_handler(client, query):
    try:
        data = query.data.split("_")
        if len(data) != 4:
            return        
        unique_id = data[1]
        search_movie = data[2]
        new_reaction = data[3]
        user_id = query.from_user.id
        emoji_map = {"heart": "❤️", "like": "👍", "dislike": "👎", "fire": "🔥"}
        if new_reaction not in emoji_map:
            return
        new_emoji = emoji_map[new_reaction]       
        if unique_id not in reaction_counts:
            return
        if user_id in user_reactions[unique_id]:
            old_emoji = user_reactions[unique_id][user_id]
            if old_emoji == new_emoji:
                return 
            else:
                reaction_counts[unique_id][old_emoji] -= 1
        user_reactions[unique_id][user_id] = new_emoji
        reaction_counts[unique_id][new_emoji] += 1
        updated_buttons = [[
            InlineKeyboardButton(f"❤️ {reaction_counts[unique_id]['❤️']}", callback_data=f"r_{unique_id}_{search_movie}_heart"),                
            InlineKeyboardButton(f"👍 {reaction_counts[unique_id]['👍']}", callback_data=f"r_{unique_id}_{search_movie}_like"),
            InlineKeyboardButton(f"👎 {reaction_counts[unique_id]['👎']}", callback_data=f"r_{unique_id}_{search_movie}_dislike"),
            InlineKeyboardButton(f"🔥 {reaction_counts[unique_id]['🔥']}", callback_data=f"r_{unique_id}_{search_movie}_fire")
        ],[
            InlineKeyboardButton('📂 Gᴇᴛ Fɪʟᴇ 📂', url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{search_movie}')
        ],[
            InlineKeyboardButton('♻️ Hᴏᴡ Tᴏ Dᴏᴡɴʟᴏᴀᴅ ♻️', url=f'https://t.me/+dVRLYHXJztJlMmY9')
        ]]
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(updated_buttons))
    except Exception as e:
        print("Reaction error:", e)
        
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
    if year is not None:
        params["year"] = str(year)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                base_url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as response:
                if response.status == 200:
                    image_data = await response.read()
                    return image_data                
                response_text = await response.text()
                if response.status == 400:
                    raise ValueError(f"Invalid request: {response_text}")
                elif response.status == 404:
                    raise ValueError(f"No poster found for: {title}")
                elif response.status == 500:
                    raise ValueError(f"Server error: {response_text}")
                else:
                    raise ValueError(f"API error: HTTP {response.status} - {response_text}")
    except aiohttp.ClientError as e:
        print(f"Network error occurred: {str(e)}")
    except asyncio.TimeoutError:
        print("Request timed out after 20 seconds")
    except ValueError as e:
        print(str(e))
    except Exception as e:
        print(f"Unexpected error: {str(e)}")   
    return None


def generate_unique_id(movie_name):
    return hashlib.md5(movie_name.encode('utf-8')).hexdigest()[:5]

async def get_qualities(text):
    qualities = ["HDCAM", "HDRip", "CAMRip", "BluRay", "WEB-DL", "WEBRip", "HDTC", "PreDVD", "DVDscr", "DVDRip", "DVDSCREEN", "HDTS", "Org", "HQ"]
    for q in qualities:
        if q.lower() in text.lower():
            return q
    return ""
    
async def get_pixels(caption):
    return next((p for p in ["480p HEVC", "480p", "720p HEVC", "720p", "1080p HEVC", "1080p", "2160p", "2K", "4K"] if p.lower() in caption.lower()), "")

async def movie_name_format(file_name):
  clean_filename = re.sub(r'http\S+', '', re.sub(r'@\w+|#\w+', '', file_name).replace('_', ' ').replace('[', '').replace(']', '').replace('(', '').replace(')', '').replace('{', '').replace('}', '').replace('.', ' ').replace('@', '').replace(':', '').replace(';', '').replace("'", '').replace('-', '').replace('!', '')).strip()
  return clean_filename


async def generate_random_filename(extension=".jpg"):
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d%H%M%S")
    sin_value = abs(math.sin(int(timestamp[-5:]))) 
    random_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))   
    filename = f"silentxbotz_{int(sin_value*10000)}_{random_part}{extension}"
    return filename
