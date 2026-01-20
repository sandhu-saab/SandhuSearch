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
from utils import clean_filename
from logging_helper import LOGGER
from typing import Optional, Dict, Any, List, Set
from datetime import datetime
from pyrogram import Client, filters
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

CAPTION_LANGUAGES = ["Bhojpuri", "Hindi", "Bengali", "Tamil", "English", "Bangla", "Telugu", "Malayalam", "Kannada", "Marathi", "Punjabi", "Bengoli", "Gujrati", "Korean", "Gujarati", "Spanish", "French", "German", "Chinese", "Arabic", "Portuguese", "Russian", "Japanese", "Odia", "Assamese", "Urdu"]

DEFAULT_IMAGE_URL = "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"

SILENTX_PREMIUM_UPDATE = """<b>{} 🆕️ <code>#{}</code>

<code>━━━━━━━━━━━━━━━━━━</code>
<b>🔈 Audio</b>: {}
<b>📺 Format</b>: {}
<b>🔰 Quality</b>: {}

<code>━━━━━━━━━━━━━━━━━━</code>
<b>🎭 Director</b>: {}
<b>📅 Release</b>: {}
<b>⭐ IMDb</b>: {}/10 (<code>{}</code> votes)
<b>🏷️ Genres</b>: {}
<code>━━━━━━━━━━━━━━━━━━</code>

⚡ Powered By @OttSandhu</b>
"""

# Cache for tracking movie update messages
movie_update_cache = {}  # Format: {movie_key: message_id}
movie_data_cache = {}    # Format: {movie_key: {'qualities': set, 'formats': set, 'audios': set}}

media_filter = filters.document | filters.video | filters.audio

@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    for file_type in ("document", "video", "audio"):
        media = getattr(message, file_type, None)
        if media is not None:
            break
    else:
        return
    media.file_type = file_type
    media.caption = message.caption
    success, silentxbotz = await save_file(media)
    try:  
        if success and silentxbotz == 1 and await get_status(bot.me.id):            
            await send_movie_update(bot, file_name=media.file_name, caption=media.caption)
    except Exception as e:
        LOGGER.error(f"Error In Movie Update - {e}")
        pass

def generate_movie_key(tmdb_data: Dict, file_name: str) -> str:
    """Generate a unique key for movie identification"""
    if tmdb_data and tmdb_data.get("id"):
        return f"tmdb_{tmdb_data['id']}"
    # Fallback to cleaned filename without quality/format info
    clean_name = re.sub(r'\b(?:480p|720p|1080p|2160p|4K|2K|HDRip|WEB-DL|WebRip|CAMRip|DVDRip|HDTC)\b', '', file_name, flags=re.IGNORECASE)
    clean_name = re.sub(r'[^\w\s]', '', clean_name).strip()
    return hashlib.md5(clean_name.lower().encode()).hexdigest()[:12]

async def get_movie_format(text: str) -> str:
    """Extract format from filename/caption (not extension)"""
    text_lower = text.lower()
    
    format_patterns = {
        "HDRip": [r'\bhdr(?:ip)?\b', r'\bhd(?:rip)?\b'],
        "WEB-DL": [r'\bweb[\s\-_]?dl\b', r'\bwebrip\b'],
        "WebRip": [r'\bwebrip\b'],
        "HDTC": [r'\bhdtc\b', r'\btelesync\b'],
        "CAM": [r'\bcam(?:rip)?\b', r'\bcam\b'],
        "CAMRip": [r'\bcamrip\b'],
        "DVDRip": [r'\bdvd(?:rip)?\b'],
        "BluRay": [r'\bblu[\s\-_]?ray\b', r'\bbdrip\b'],
        "HDCAM": [r'\bhdcam\b'],
        "HDTS": [r'\bhdts\b'],
        "DVDScreener": [r'\bdvdscreener\b', r'\bscreener\b'],
        "HDTV": [r'\bhdtv\b'],
        "PDTV": [r'\bpdtv\b'],
        "BRRip": [r'\bbrrip\b'],
        "BDRip": [r'\bbdrip\b'],
        "HQ": [r'\bhq\b'],
        "ORIGINAL": [r'\boriginal\b', r'\buntouched\b'],
        "ORG": [r'\borg\b'],
    }
    
    found_formats = set()
    for format_name, patterns in format_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                found_formats.add(format_name)
    
    # Default fallback
    if not found_formats:
        return "HDRip"
    
    # Prioritize certain formats
    priority_formats = ["WEB-DL", "BluRay", "HDRip", "DVDRip"]
    for fmt in priority_formats:
        if fmt in found_formats:
            return fmt
    
    return list(found_formats)[0]

def escape_html(text: str) -> str:
    if not text:
        return ""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def get_trailer_button(tmdb_data: Dict) -> list:
    videos = tmdb_data.get("videos", [])
    yt_videos = [v for v in videos if "youtube" in v.get("url", "").lower()]    
    if yt_videos:
        return [InlineKeyboardButton("▶️ Watch Trailer", url=yt_videos[0]["url"])]
    return []

async def send_with_visual(bot, caption: str, tmdb_data: Dict, search_movie, message_id=None):
    """Send or edit movie update with visual"""
    try:
        get_file = f'https://telegram.me/{temp.U_NAME}?start=getfile-{search_movie}'
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔎Tap to Search", url=get_file)],
            get_trailer_button(tmdb_data)
        ])
        
        # If message_id provided, edit existing message
        if message_id:
            try:
                # Try to edit photo first (if we have photo)
                visual_url = await get_best_visual(tmdb_data)
                if visual_url:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(visual_url, timeout=aiohttp.ClientTimeout(total=20)) as img_resp:
                            if img_resp.status == 200:
                                img_bytes = await img_resp.read()
                                photo_file = io.BytesIO(img_bytes)
                                photo_file.name = await generate_premium_filename(tmdb_data["title"])
                                
                                await bot.edit_message_media(
                                    chat_id=MOVIE_UPDATE_CHANNEL,
                                    message_id=message_id,
                                    media=InputMediaPhoto(
                                        media=photo_file,
                                        caption=caption,
                                        parse_mode=ParseMode.HTML
                                    ),
                                    reply_markup=keyboard
                                )
                                return
                
                # If no photo or edit fails, just edit caption
                await bot.edit_message_caption(
                    chat_id=MOVIE_UPDATE_CHANNEL,
                    message_id=message_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
                return
                
            except Exception as e:
                LOGGER.error(f"Edit message error: {e}")
                # Fallback to sending new message
                message_id = None
        
        # Send new message
        if not message_id:
            visual_url = await get_best_visual(tmdb_data)
            
            if visual_url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(visual_url, timeout=aiohttp.ClientTimeout(total=20)) as img_resp:
                        if img_resp.status == 200:
                            img_bytes = await img_resp.read()
                            photo_file = io.BytesIO(img_bytes)
                            photo_file.name = await generate_premium_filename(tmdb_data["title"])
                            
                            message = await bot.send_photo(
                                chat_id=MOVIE_UPDATE_CHANNEL, 
                                photo=photo_file, 
                                caption=caption,
                                parse_mode=ParseMode.HTML,
                                reply_markup=keyboard
                            )
                            return message.id
            
            # Fallback to default image
            message = await bot.send_photo(
                chat_id=MOVIE_UPDATE_CHANNEL,
                photo=DEFAULT_IMAGE_URL,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            return message.id
            
    except Exception as e:
        LOGGER.error(f"Visual Send/Edit Error: {e}")
        return None

async def generate_premium_filename(title: str, extension=".jpg") -> str:
    clean_title = re.sub(r'[^\w\s-]', '', title)[:20].strip()
    timestamp = datetime.now().strftime("%y%m%d%H%M")
    unique_id = hashlib.md5(title.encode()).hexdigest()[:6]
    return f"silentx_{clean_title}_{timestamp}_{unique_id}{extension}"

async def get_languages(text: str) -> Set[str]:
    """Return set of languages found in text"""
    text_lower = text.lower().replace(" ", "")
    found_langs = set()
    
    for lang in CAPTION_LANGUAGES:
        lang_lower = lang.lower().replace(" ", "")
        if lang_lower in text_lower:
            found_langs.add(lang)
    
    return found_langs

async def get_qualities(text: str) -> Set[str]:
    """Return set of qualities (resolutions) found in text"""
    qualities = set()
    quality_patterns = {
        "480p": [r'\b480p\b', r'\bsd\b'],
        "720p": [r'\b720p\b', r'\bhd\b(?!rip)', r'\bhdr\b(?!ip)'],
        "1080p": [r'\b1080p\b', r'\bfullhd\b', r'\bfhd\b'],
        "2160p": [r'\b2160p\b', r'\b4k\b', r'\buhd\b'],
        "2K": [r'\b2k\b'],
        "1440p": [r'\b1440p\b', r'\bqhd\b'],
    }
    
    text_lower = text.lower()
    for quality, patterns in quality_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                qualities.add(quality)
                break
    
    return qualities

async def get_pixels(caption: str) -> Set[str]:
    """Legacy function - use get_qualities instead"""
    pixels = set()
    pixel_patterns = [
        r'\b480p\b',
        r'\b480p HEVC\b',
        r'\b720p\b',
        r'\b720p HEVC\b',
        r'\b1080p\b',
        r'\b1080p HEVC\b',
        r'\b2160p\b',
        r'\b2K\b',
        r'\b4K\b'
    ]
    
    for pattern in pixel_patterns:
        if re.search(pattern, caption, re.IGNORECASE):
            match = re.search(pattern, caption, re.IGNORECASE)
            if match:
                pixels.add(match.group(0))
    
    return pixels

async def send_movie_update(bot, file_name, caption):
    """Send or edit movie update message"""
    try:
        file_name = clean_filename(file_name)
        caption = clean_filename(caption)
        
        # Extract year
        year_match = re.search(r"\b(19|20)\d{2}\b", caption)
        year = year_match.group(0) if year_match else None      
        
        # Extract season
        season_match = re.search(r"(?i)(?:s|season)0*(\d{1,2})", caption) or re.search(r"(?i)(?:s|season)0*(\d{1,2})", file_name)
        
        if year:
            file_name = file_name[:file_name.find(year) + 4]
        elif season_match:
            season = season_match.group(1)
            file_name = file_name[:file_name.find(season) + 1]
        
        # Extract current file's metadata
        current_format = await get_movie_format(caption + " " + file_name)
        current_qualities = await get_qualities(caption + " " + file_name)
        current_audios = await get_languages(caption + " " + file_name)
        
        # Get TMDB data
        tmdb_data = await fetch_tmdb_data(file_name, year)
        if not tmdb_data:
            return 
        
        # Generate movie key for tracking
        movie_key = generate_movie_key(tmdb_data, file_name)
        search_movie = file_name.replace(" ", "-")
        
        director = tmdb_data.get("director", "")
        if not director or not director.strip():
            director = "N/A"
        
        # Check if we already have an update for this movie
        if movie_key in movie_update_cache:
            # Edit existing message
            message_id = movie_update_cache[movie_key]
            
            # Update cached data
            if movie_key not in movie_data_cache:
                movie_data_cache[movie_key] = {
                    'formats': set(),
                    'qualities': set(),
                    'audios': set()
                }
            
            # Add current data to cache
            movie_data_cache[movie_key]['formats'].add(current_format)
            movie_data_cache[movie_key]['qualities'].update(current_qualities)
            movie_data_cache[movie_key]['audios'].update(current_audios)
            
            # Prepare strings for display
            formats_str = ", ".join(sorted(movie_data_cache[movie_key]['formats']))
            qualities_str = ", ".join(sorted(movie_data_cache[movie_key]['qualities']))
            audios_str = ", ".join(sorted(movie_data_cache[movie_key]['audios']))
            
            if not audios_str:
                audios_str = "Multi-Audio"
            if not formats_str:
                formats_str = "HDRip"
            if not qualities_str:
                qualities_str = "720p"
            
        else:
            # New movie - send new message
            formats_str = current_format
            qualities_str = ", ".join(sorted(current_qualities)) if current_qualities else "720p"
            audios_str = ", ".join(sorted(current_audios)) if current_audios else "Multi-Audio"
            
            # Initialize cache
            movie_data_cache[movie_key] = {
                'formats': {current_format},
                'qualities': current_qualities.copy(),
                'audios': current_audios.copy()
            }
        
        # Build caption
        full_caption = SILENTX_PREMIUM_UPDATE.format(
            escape_html(tmdb_data["title"]),
            tmdb_data["kind"],
            escape_html(audios_str),
            escape_html(formats_str),
            escape_html(qualities_str),
            escape_html(director),
            escape_html(tmdb_data["release_date"] or "TBA"),
            tmdb_data["vote_average"],
            tmdb_data["vote_count"],
            escape_html(", ".join(tmdb_data["genres"][:3]))
        )
        
        # Send or edit message
        message_id = await send_with_visual(
            bot, 
            full_caption, 
            tmdb_data, 
            search_movie,
            message_id=movie_update_cache.get(movie_key)
        )
        
        # Update cache with new message ID
        if message_id:
            movie_update_cache[movie_key] = message_id
        
    except Exception as e:
        LOGGER.error(f"Error In Movie Update: {e}")

# Helper function for compatibility
async def get_best_visual(tmdb_data: Dict) -> Optional[str]:
    """Get best visual (poster/backdrop) from TMDB data"""
    try:
        if tmdb_data.get("poster_path"):
            return f"https://image.tmdb.org/t/p/original{tmdb_data['poster_path']}"
        elif tmdb_data.get("backdrop_path"):
            return f"https://image.tmdb.org/t/p/original{tmdb_data['backdrop_path']}"
        return None
    except:
        return None

# Optional: Add periodic cache cleanup
async def cleanup_cache():
    """Clean old cache entries periodically"""
    while True:
        await asyncio.sleep(3600)  # Clean every hour
        try:
            # Remove cache entries older than 24 hours
            # You can implement this if needed
            pass
        except:
            pass

# Start cleanup task if not already started
try:
    asyncio.create_task(cleanup_cache())
except:
    pass
