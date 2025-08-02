import re
import io
import random
import string
import aiohttp
import asyncio
import hashlib
from info import *
from utils import *
from typing import Optional, Dict, Set
from datetime import datetime
from pyrogram import Client, filters
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== सेटिंग्स ========== #
MAX_CALLBACK_SIZE = 64  # Telegram की लिमिट
CAPTION_LANGUAGES = ["Bhojpuri", "Hindi", "Bengali", "Tamil", "English", 
                    "Bangla", "Telugu", "Malayalam", "Kannada", "Marathi",
                    "Punjabi", "Bengoli", "Gujrati", "Korean", "Gujarati",
                    "Spanish", "French", "German", "Chinese", "Arabic",
                    "Portuguese", "Russian", "Japanese", "Odia", "Assamese", "Urdu"]
POSTER_API_URL = "https://image.silentxbotz.tech/api/v1/poster"
HOW_TO_DOWNLOAD_URL = "https://t.me/+dVRLYHXJztJlMmY9"
DEFAULT_POSTER_URL = "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"

# ========== ग्लोबल डेटा ========== #
movie_data: Dict[str, dict] = {}
reaction_counts: Dict[str, dict] = {}
user_reactions: Dict[str, dict] = {}

# ========== हेल्पर फंक्शन्स ========== #
def generate_short_id(movie_name: str) -> str:
    """छोटा मूवी आईडी बनाएं"""
    return hashlib.md5(movie_name.encode()).hexdigest()[:6]  # सिर्फ 6 करैक्टर

def clean_text(text: str) -> str:
    """टेक्स्ट को साफ करें"""
    return re.sub(r'[^\w\s-]', '', text).strip()

async def compress_search_query(query: str) -> str:
    """सर्च क्वेरी को छोटा करें"""
    # स्पेशल करैक्टर हटाएं और 20 करैक्टर तक सीमित करें
    compressed = re.sub(r'[^a-z0-9]+', '-', query.lower())[:20]
    return compressed.rstrip('-')

def quality_sort_key(quality: str) -> int:
    """क्वालिटी सॉर्ट करने के लिए"""
    order = {"480p": 1, "720p": 2, "1080p": 3, "2160p": 4, "4k": 5}
    return order.get(quality.lower(), 0)

# ========== डेटा एक्सट्रैक्शन फंक्शन्स ========== #
async def extract_items(text: str, items: list) -> Set[str]:
    """फॉर्मेट/क्वालिटी/भाषा निकालें"""
    found = set()
    text_lower = text.lower()
    for item in items:
        if re.search(rf"\b{re.escape(item.lower())}\b", text_lower):
            found.add(item)
    return found

async def extract_formats(text: str) -> Set[str]:
    formats = ["ORG", "HDRip", "WEB-DL", "WEBRip", "HDCAM", "HQ", 
              "CAMRip", "HDTC", "DVDscr", "dvdrip", "dvdscreen", "HDTS"]
    return await extract_items(text, formats)

async def extract_qualities(text: str) -> Set[str]:
    qualities = ["480p", "720p", "1080p", "2160p", "4K", "2K"]
    return await extract_items(text, qualities)

async def extract_languages(text: str) -> Set[str]:
    return await extract_items(text, CAPTION_LANGUAGES)

async def extract_ott(text: str) -> Set[str]:
    """OTT प्लेटफॉर्म निकालें"""
    ott_keywords = {
        "Netflix": ["nf", "netflix"],
        "SonyLiv": ["sonyliv", "sony", "sliv"],
        "Amazon Prime Video": ["amzn", "prime", "primevideo"],
        "Disney+ Hotstar": ["hotstar"],
        "Zee5": ["zee5"],
        "JioHotstar": ["jio", "jhs"],
        "Aha": ["aha"],
        "HBO Max": ["hbo"],
        "Paramount+": ["paramount"],
        "Apple TV+": ["apple"],
        "Hoichoi": ["hoichoi"],
        "Sun NXT": ["sunnxt"],
        "Viki": ["viki"],
        "ChaupalTV": ["chtv", "chpl", "chaupal"],
        "KABLEONE": ["kableone"]
    }
    found = set()
    text_lower = text.lower()
    for platform, keywords in ott_keywords.items():
        if any(re.search(rf"\b{re.escape(k)}\b", text_lower) for k in keywords):
            found.add(platform)
    return found

# ========== मूवी अपडेट हैंडलर ========== #
@Client.on_message(filters.chat(CHANNELS) & (filters.document | filters.video | filters.audio))
async def media_handler(bot: Client, message):
    """मीडिया हैंडलर"""
    media = next(
        (getattr(message, attr) for attr in ("document", "video", "audio") 
        if getattr(message, attr, None)
    ), None)
    
    if not media:
        return
    
    media.file_type = next(attr for attr in ("document", "video", "audio") if getattr(message, attr, None))
    media.caption = message.caption or ""
    
    try:
        success, _ = await save_file(media)
        if success and await get_status(bot.me.id):
            await process_movie_update(bot, media.file_name, media.caption)
    except Exception as e:
        print(f"❌ मीडिया हैंडलर में एरर: {e}")

async def process_movie_update(bot: Client, file_name: str, caption: str):
    """मूवी अपडेट प्रोसेस करें"""
    try:
        # डेटा साफ करें
        clean_name = clean_text(file_name)
        clean_caption = clean_text(caption)
        
        # मूवी आईडी जेनरेट करें
        movie_id = generate_short_id(clean_name)
        
        # सर्च क्वेरी को कंप्रेस करें
        search_query = await compress_search_query(clean_name)
        
        # मेटाडेटा निकालें
        year_match = re.search(r"\b(19|20)\d{2}\b", clean_caption)
        year = year_match.group(0) if year_match else None
        
        formats = await extract_formats(clean_caption)
        qualities = await extract_qualities(clean_caption)
        languages = await extract_languages(clean_caption)
        ott = await extract_ott(clean_caption)
        
        # मूवी डेटा अपडेट करें
        if movie_id not in movie_data:
            movie_data[movie_id] = {
                'formats': set(),
                'qualities': set(),
                'languages': set(),
                'ott': set(),
                'message_id': None,
                'search_query': search_query
            }
            reaction_counts[movie_id] = {"❤️": 0, "👍": 0, "👎": 0, "🔥": 0}
            user_reactions[movie_id] = {}
        
        # डेटा अपडेट करें
        movie_data[movie_id]['formats'].update(formats)
        movie_data[movie_id]['qualities'].update(qualities)
        movie_data[movie_id]['languages'].update(languages)
        movie_data[movie_id]['ott'].update(ott)
        
        # IMDb डेटा फेच करें
        imdb_data = await get_imdb_details(clean_name)
        title = imdb_data.get("title", clean_name)
        rating = imdb_data.get("rating", "N/A")
        genres = imdb_data.get("genres", "N/A")
        
        # कैप्शन बनाएं
        caption_lines = [f"<b>【{clean_name}】🆕️</b>", ""]
        
        if ott_str := ", ".join(sorted(movie_data[movie_id]['ott'])): 
            caption_lines.append(f"<b>📀 OTT - {ott_str}</b>")
        
        if rating != "N/A" and rating:
            if not rating.endswith('★'):
                rating += '★'
            caption_lines.append(f"<b>⭐️ Rᴀᴛɪɴɢ - {rating}</b>")
        
        if format_str := ", ".join(sorted(movie_data[movie_id]['formats'])): 
            caption_lines.append(f"<b>📺 Fᴏʀᴍᴀᴛ - {format_str}</b>")
        
        if quality_str := ", ".join(sorted(movie_data[movie_id]['qualities'], key=quality_sort_key)):
            caption_lines.append(f"<b>🔰 Qᴜᴀʟɪᴛʏ - {quality_str}</b>")
        
        if language_str := ", ".join(sorted(movie_data[movie_id]['languages'])): 
            caption_lines.append(f"<b>🔈 Aᴜᴅɪᴏ - {language_str}</b>")
        
        if genres != "N/A" and genres:
            caption_lines.append(f"<b>🎭 Gᴇɴʀᴇꜱ - {genres}</b>")
        
        caption_lines.extend(["", f"<blockquote>👑 Pʀᴏᴠɪᴅᴇᴅ Bʏ : {PROVIDER_NAME}</blockquote>"])
        full_caption = "\n".join(caption_lines)
        
        # बटन बनाएं (नया डिजाइन)
        buttons = [
            [
                InlineKeyboardButton(f"❤️ {reaction_counts[movie_id]['❤️']}", callback_data=f"h:{movie_id}"),
                InlineKeyboardButton(f"👍 {reaction_counts[movie_id]['👍']}", callback_data=f"l:{movie_id}"),
                InlineKeyboardButton(f"👎 {reaction_counts[movie_id]['👎']}", callback_data=f"d:{movie_id}"),
                InlineKeyboardButton(f"🔥 {reaction_counts[movie_id]['🔥']}", callback_data=f"f:{movie_id}")
            ],
            [
                InlineKeyboardButton('📂 Gᴇᴛ Fɪʟᴇ 📂', url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{search_query}')
            ],
            [
                InlineKeyboardButton('♻️ Hᴏᴡ Tᴏ Dᴏᴡɴʟᴏᴀᴅ ♻️', url=HOW_TO_DOWNLOAD_URL)
            ]
        ]
        
        # मौजूदा मैसेज को एडिट करें
        if msg_id := movie_data[movie_id]['message_id']:
            try:
                await bot.edit_message_caption(
                    chat_id=MOVIE_UPDATE_CHANNEL,
                    message_id=msg_id,
                    caption=full_caption,
                    reply_markup=InlineKeyboardMarkup(buttons)
                print(f"✅ अपडेट हुआ: {clean_name}")
                return
            except Exception:
                movie_data[movie_id]['message_id'] = None  # रीसेट करें अगर एडिट फेल हो
        
        # नया मैसेज भेजें
        poster = await fetch_movie_poster(title, year)
        try:
            if poster:
                photo_file = io.BytesIO(poster)
                photo_file.name = f"poster_{movie_id}.jpg"
                sent = await bot.send_photo(
                    chat_id=MOVIE_UPDATE_CHANNEL,
                    photo=photo_file,
                    caption=full_caption,
                    reply_markup=InlineKeyboardMarkup(buttons)
            else:
                sent = await bot.send_photo(
                    chat_id=MOVIE_UPDATE_CHANNEL,
                    photo=DEFAULT_POSTER_URL,
                    caption=full_caption,
                    reply_markup=InlineKeyboardMarkup(buttons))
            
            movie_data[movie_id]['message_id'] = sent.id
            print(f"📤 नया मूवी: {clean_name}")
        except Exception as e:
            print(f"❌ मैसेज भेजने में एरर: {e}")
            
    except Exception as e:
        print(f"❌ मूवी अपडेट एरर: {e}")

# ========== रिएक्शन हैंडलर ========== #
@Client.on_callback_query(filters.regex(r"^[hldf]:"))
async def reaction_handler(client, query):
    """रिएक्शन अपडेट करें"""
    try:
        # डेटा पार्स करें
        reaction_code, movie_id = query.data.split(":", 1)
        
        # वैलिडेट करें
        if movie_id not in reaction_counts or movie_id not in user_reactions:
            await query.answer("⚠️ मूवी नहीं मिली!", show_alert=True)
            return
        
        # इमोजी मैपिंग
        emoji_map = {
            "h": "❤️",
            "l": "👍",
            "d": "👎",
            "f": "🔥"
        }
        new_emoji = emoji_map.get(reaction_code)
        if not new_emoji:
            return
        
        user_id = query.from_user.id
        current_reaction = user_reactions[movie_id].get(user_id)
        
        # अगर यूजर ने पहले ही रिएक्ट किया हुआ है
        if current_reaction == new_emoji:
            await query.answer("👍 आप पहले ही रिएक्ट कर चुके हैं!")
            return
        
        # काउंटर अपडेट करें
        if current_reaction:
            reaction_counts[movie_id][current_reaction] -= 1
            
        reaction_counts[movie_id][new_emoji] += 1
        user_reactions[movie_id][user_id] = new_emoji
        
        # नए बटन बनाएं
        buttons = [
            [
                InlineKeyboardButton(f"❤️ {reaction_counts[movie_id]['❤️']}", callback_data=f"h:{movie_id}"),
                InlineKeyboardButton(f"👍 {reaction_counts[movie_id]['👍']}", callback_data=f"l:{movie_id}"),
                InlineKeyboardButton(f"👎 {reaction_counts[movie_id]['👎']}", callback_data=f"d:{movie_id}"),
                InlineKeyboardButton(f"🔥 {reaction_counts[movie_id]['🔥']}", callback_data=f"f:{movie_id}")
            ],
            [
                InlineKeyboardButton('📂 Gᴇᴛ Fɪʟᴇ 📂', 
                                    url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{movie_data[movie_id]["search_query"]}')
            ],
            [
                InlineKeyboardButton('♻️ Hᴏᴡ Tᴏ Dᴏᴡɴʟᴏᴀᴅ ♻️', url=HOW_TO_DOWNLOAD_URL)
            ]
        ]
        
        # मैसेज अपडेट करें
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
        await query.answer(f"✅ {new_emoji} रिएक्शन अपडेट हो गया!")
        
    except Exception as e:
        print(f"❌ रिएक्शन एरर: {e}")
        await query.answer("⚠️ एरर आया! बाद में ट्राई करें", show_alert=True)

# ========== पोस्टर फंक्शन्स ========== #
async def get_imdb_details(name: str) -> dict:
    """IMDb डेटा फेच करें"""
    try:
        formatted_name = clean_text(name)
        imdb = await get_poster(formatted_name)
        return imdb or {}
    except Exception as e:
        print(f"❌ IMDb फेच एरर: {e}")
        return {}

async def fetch_movie_poster(title: str, year: Optional[int] = None) -> Optional[bytes]:
    """मूवी पोस्टर फेच करें"""
    try:
        params = {"title": clean_text(title)}
        if year:
            params["year"] = str(year)
            
        async with aiohttp.ClientSession() as session:
            async with session.get(POSTER_API_URL, params=params, timeout=10) as response:
                if response.status == 200:
                    return await response.read()
                print(f"⚠️ पोस्टर API एरर: HTTP {response.status}")
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        print(f"🌐 नेटवर्क एरर: {type(e).__name__}")
    return None
