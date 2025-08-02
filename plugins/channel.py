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

# सभी भाषाएँ और जेनर
CAPTION_LANGUAGES = ["Bhojpuri", "Hindi", "Bengali", "Tamil", "English", "Bangla", "Telugu", "Malayalam", "Kannada", "Marathi", "Punjabi", "Bengoli", "Gujrati", "Korean", "Gujarati", "Spanish", "French", "German", "Chinese", "Arabic", "Portuguese", "Russian", "Japanese", "Odia", "Assamese", "Urdu"]
MOVIE_GENRES = ["Action", "Adventure", "Animation", "Biography", "Comedy", "Crime", "Documentary", "Drama", "Family", "Fantasy", "Film-Noir", "History", "Horror", "Music", "Musical", "Mystery", "Romance", "Sci-Fi", "Sport", "Thriller", "War", "Western"]

# ग्लोबल स्टोरेज
movie_data = {}  # key: movie_id, value: { 'message_id': int, 'formats': set, 'qualities': set, 'languages': set, 'ott': set }
reaction_counts = {}
user_reactions = {}

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
    success, silentxbotz = await save_file(media)
    
    try:  
        if success and silentxbotz == 1 and await get_status(bot.me.id):            
            await send_movie_update(bot, file_name=media.file_name, caption=media.caption)
    except Exception as e:
        print(f"❌ Error In Movie Update - {e}")

async def send_movie_update(bot, file_name, caption):
    try:
        # मूवी नाम और कैप्शन को साफ करें
        clean_name = await movie_name_format(file_name)
        clean_caption = await movie_name_format(caption)
        
        # साल और सीजन निकालें
        year = re.search(r"\b(19|20)\d{2}\b", clean_caption)
        year = year.group(0) if year else None
        
        # मूवी आईडी जेनरेट करें (नाम के आधार पर)
        movie_id = generate_movie_id(clean_name)
        
        # फ़ॉर्मेट, क्वालिटी, लैंग्वेज और OTT निकालें
        formats = await extract_formats(clean_caption)
        qualities = await extract_qualities(clean_caption)
        languages = await extract_languages(clean_caption)
        ott = await extract_ott(clean_caption)
        
        # IMDb डेटा फेच करें
        imdb_data = await get_imdb_details(clean_name)
        title = imdb_data.get("title", clean_name)
        kind = imdb_data.get("kind", "").strip().upper().replace(" ", "_") if imdb_data else ""
        rating = imdb_data.get("rating", "N/A")
        genres = imdb_data.get("genres", "N/A")
        
        # सर्च क्वेरी जेनरेट करें
        search_movie = clean_name.replace(" ", "-")
        
        # अगर यह मूवी पहले से मौजूद है तो डेटा अपडेट करें
        if movie_id in movie_data:
            # फ़ॉर्मेट, क्वालिटी, लैंग्वेज को अपडेट करें
            movie_data[movie_id]['formats'].update(formats)
            movie_data[movie_id]['qualities'].update(qualities)
            movie_data[movie_id]['languages'].update(languages)
            movie_data[movie_id]['ott'].update(ott)
        else:
            # नया मूवी डेटा क्रिएट करें
            movie_data[movie_id] = {
                'formats': set(formats),
                'qualities': set(qualities),
                'languages': set(languages),
                'ott': set(ott),
                'message_id': None
            }
            # रिएक्शन काउंटर इनिशियलाइज़ करें
            reaction_counts[movie_id] = {"❤️": 0, "👍": 0, "👎": 0, "🔥": 0}
            user_reactions[movie_id] = {}
        
        # डेटा सेट से स्ट्रिंग बनाएं
        format_str = ", ".join(sorted(movie_data[movie_id]['formats']))
        quality_str = ", ".join(sorted(movie_data[movie_id]['qualities'], key=quality_sort_key))
        language_str = ", ".join(sorted(movie_data[movie_id]['languages']))
        ott_str = ", ".join(sorted(movie_data[movie_id]['ott']))
        
        # आपके डिज़ाइन के अनुसार कैप्शन बनाएं
        caption_lines = [f"<b>【{clean_name}】🆕️</b>", ""]
        
        # OTT (केवल अगर उपलब्ध हो)
        if ott_str:
            caption_lines.append(f"<b>📀 OTT - {ott_str}</b>")
        
        # रेटिंग (केवल अगर उपलब्ध हो)
        if rating and rating != "N/A":
            # अगर रेटिंग में पहले से स्टार नहीं है तो जोड़ें
            if '★' not in rating:
                rating += '★'
            caption_lines.append(f"<b>⭐️ Rᴀᴛɪɴɢ - {rating}</b>")
        
        # फॉर्मेट (केवल अगर उपलब्ध हो)
        if format_str:
            caption_lines.append(f"<b>📺 Fᴏʀᴍᴀᴛ - {format_str}</b>")
        
        # क्वालिटी (केवल अगर उपलब्ध हो)
        if quality_str:
            caption_lines.append(f"<b>🔰 Qᴜᴀʟɪᴛʏ - {quality_str}</b>")
        
        # भाषा (केवल अगर उपलब्ध हो)
        if language_str:
            caption_lines.append(f"<b>🔈 Aᴜᴅɪᴏ - {language_str}</b>")
        
        # जेनर (केवल अगर उपलब्ध हो)
        if genres and genres != "N/A":
            caption_lines.append(f"<b>🎭 Gᴇɴʀᴇꜱ - {genres}</b>")
        
        # प्रोवाइडेड बाय लाइन
        caption_lines.append("")
        caption_lines.append(f"<blockquote>👑 Pʀᴏᴠɪᴅᴇᴅ Bʏ : {PROVIDER_NAME}</blockquote>")
        
        full_caption = "\n".join(caption_lines)
        
        # बटन बनाएं
        buttons = [[
            InlineKeyboardButton(f"❤️ {reaction_counts[movie_id]['❤️']}", callback_data=f"r_{movie_id}_{search_movie}_heart"),                
            InlineKeyboardButton(f"👍 {reaction_counts[movie_id]['👍']}", callback_data=f"r_{movie_id}_{search_movie}_like"),
            InlineKeyboardButton(f"👎 {reaction_counts[movie_id]['👎']}", callback_data=f"r_{movie_id}_{search_movie}_dislike"),
            InlineKeyboardButton(f"🔥 {reaction_counts[movie_id]['🔥']}", callback_data=f"r_{movie_id}_{search_movie}_fire")
        ],[
            InlineKeyboardButton('Get File', url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{search_movie}')
        ]]
        
        # चेक करें कि क्या पहले से मैसेज है
        if movie_data[movie_id]['message_id']:
            try:
                # मौजूदा मैसेज को एडिट करें
                await bot.edit_message_caption(
                    chat_id=MOVIE_UPDATE_CHANNEL,
                    message_id=movie_data[movie_id]['message_id'],
                    caption=full_caption,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                print(f"✅ Updated message for {clean_name}")
                return
            except Exception as e:
                print(f"❌ Error editing message: {e}")
                # अगर एडिट फेल हो तो मैसेज आईडी रीसेट करें
                movie_data[movie_id]['message_id'] = None
        
        # नया मैसेज भेजें
        poster = await fetch_movie_poster(title, year)
        if poster:
            photo_file = io.BytesIO(poster)
            photo_file.name = await generate_random_filename()
            sent_message = await bot.send_photo(
                chat_id=MOVIE_UPDATE_CHANNEL, 
                photo=photo_file, 
                caption=full_caption, 
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            image_url = "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"   
            sent_message = await bot.send_photo(
                chat_id=MOVIE_UPDATE_CHANNEL, 
                photo=image_url, 
                caption=full_caption, 
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        
        # मैसेज आईडी को स्टोर करें
        movie_data[movie_id]['message_id'] = sent_message.id
        print(f"📤 Sent new message for {clean_name}")
                
    except Exception as e:
        print(f"❌ Error in send_movie_update: {e}")

@Client.on_callback_query(filters.regex(r"^r_"))
async def reaction_handler(client, query):
    try:
        data = query.data.split("_")
        if len(data) != 4:
            return        
        movie_id = data[1]
        search_movie = data[2]
        new_reaction = data[3]
        user_id = query.from_user.id
        
        emoji_map = {"heart": "❤️", "like": "👍", "dislike": "👎", "fire": "🔥"}
        if new_reaction not in emoji_map:
            return
        
        new_emoji = emoji_map[new_reaction]       
        if movie_id not in reaction_counts:
            return
        
        if user_id in user_reactions[movie_id]:
            old_emoji = user_reactions[movie_id][user_id]
            if old_emoji == new_emoji:
                return 
            else:
                reaction_counts[movie_id][old_emoji] -= 1
        
        user_reactions[movie_id][user_id] = new_emoji
        reaction_counts[movie_id][new_emoji] += 1
        
        # बटन्स अपडेट करें
        updated_buttons = [[
            InlineKeyboardButton(f"❤️ {reaction_counts[movie_id]['❤️']}", callback_data=f"r_{movie_id}_{search_movie}_heart"),                
            InlineKeyboardButton(f"👍 {reaction_counts[movie_id]['👍']}", callback_data=f"r_{movie_id}_{search_movie}_like"),
            InlineKeyboardButton(f"👎 {reaction_counts[movie_id]['👎']}", callback_data=f"r_{movie_id}_{search_movie}_dislike"),
            InlineKeyboardButton(f"🔥 {reaction_counts[movie_id]['🔥']}", callback_data=f"r_{movie_id}_{search_movie}_fire")
        ],[
            InlineKeyboardButton('Get File', url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{search_movie}')
        ]]
        
        # मैसेज को एडिट करें
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(updated_buttons))
    except Exception as e:
        print("❌ Reaction error:", e)
        
async def get_imdb_details(name):
    try:
        formatted_name = await movie_name_format(name)
        imdb = await get_poster(formatted_name)
        if not imdb:
            return {}
        return {
            "title": imdb.get("title", formatted_name),
            "kind": imdb.get("kind", ""),
            "year": imdb.get("year"),
            "rating": imdb.get("rating", ""),
            "genres": ", ".join(imdb.get("genres", [])),
            "url" : imdb.get("url", "")
        }
    except Exception as e:
        print(f"❌ IMDB fetch error: {e}")
        return {}

async def fetch_movie_poster(title: str, year: Optional[int] = None) -> Optional[bytes]:
    """Fetch movie poster from API with detailed error handling"""
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
                    return await response.read()
                
                response_text = await response.text()
                if response.status == 400:
                    print(f"❌ Invalid request for {title}: {response_text}")
                elif response.status == 404:
                    print(f"🚫 No poster found for: {title}")
                elif response.status == 500:
                    print(f"⚠️ Server error for {title}: {response_text}")
                else:
                    print(f"❗ API error for {title}: HTTP {response.status} - {response_text}")
    except aiohttp.ClientError as e:
        print(f"🌐 Network error for {title}: {str(e)}")
    except asyncio.TimeoutError:
        print(f"⏰ Request timed out for {title}")
    except Exception as e:
        print(f"💥 Unexpected error for {title}: {str(e)}")
    
    return None

def generate_movie_id(movie_name):
    """मूवी के लिए यूनिक आईडी बनाएं"""
    return hashlib.md5(movie_name.encode('utf-8')).hexdigest()[:8]

def quality_sort_key(quality):
    """क्वालिटी को सॉर्ट करने के लिए की"""
    order = {"480p": 1, "720p": 2, "1080p": 3, "2160p": 4, "4K": 5}
    for k, v in order.items():
        if k in quality:
            return v
    return 0

async def extract_formats(text):
    """टेक्स्ट से सभी फ़ॉर्मेट निकालें"""
    formats = ["ORG", "HDRip", "WEB-DL", "WEBRip", "HDCAM", "HQ", "CAMRip", 
               "HDTC", "DVDscr", "dvdrip", "dvdscreen", "HDTS"]
    found = set()
    for f in formats:
        if re.search(rf"\b{re.escape(f)}\b", text, re.IGNORECASE):
            found.add(f)
    return found

async def extract_qualities(text):
    """टेक्स्ट से सभी क्वालिटी निकालें"""
    qualities = ["480p", "720p", "1080p", "2160p", "4K", "2K"]
    found = set()
    for q in qualities:
        if re.search(rf"\b{re.escape(q)}\b", text, re.IGNORECASE):
            found.add(q)
    return found

async def extract_languages(text):
    """टेक्स्ट से सभी भाषाएँ निकालें"""
    found = set()
    for lang in CAPTION_LANGUAGES:
        if re.search(rf"\b{re.escape(lang)}\b", text, re.IGNORECASE):
            found.add(lang)
    return found

async def extract_ott(text):
    """टेक्स्ट से सभी OTT प्लेटफॉर्म निकालें"""
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
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword)}\b", text_lower):
                found.add(platform)
                break
    
    return found

async def movie_name_format(file_name):
    """मूवी नाम को साफ करें"""
    # अनावश्यक टेक्स्ट हटाएं
    clean_filename = re.sub(
        r'http\S+|@\w+|#\w+|[\[\](){}.:;@!]|_|-', 
        ' ', 
        file_name
    )
    # एक्स्ट्रा स्पेस हटाएं
    clean_filename = re.sub(r'\s+', ' ', clean_filename).strip()
    return clean_filename

async def generate_random_filename(extension=".jpg"):
    """रैंडम फाइल नाम जेनरेट करें"""
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d%H%M%S")
    random_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))   
    return f"silentx_{timestamp}_{random_part}{extension}"