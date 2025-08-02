import re
import io
import aiohttp
import asyncio
import hashlib
from info import *
from utils import *
from typing import Optional, Dict, Set, Tuple, Any
from pyrogram import Client, filters
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified

# ========== SETTINGS ========== #
MAX_CALLBACK_SIZE = 64
CAPTION_LANGUAGES = ["Bhojpuri", "Hindi", "Bengali", "Tamil", "English", 
                    "Bangla", "Telugu", "Malayalam", "Kannada", "Marathi",
                    "Punjabi", "Bengoli", "Gujrati", "Korean", "Gujarati",
                    "Spanish", "French", "German", "Chinese", "Arabic",
                    "Portuguese", "Russian", "Japanese", "Odia", "Assamese", "Urdu"]
POSTER_API_URL = "https://image.silentxbotz.tech/api/v1/poster"
HOW_TO_DOWNLOAD_URL = "https://t.me/+dVRLYHXJztJlMmY9"
DEFAULT_POSTER_URL = "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"

# Enhanced patterns to remove all unwanted text
TITLE_CLEAN_PATTERNS = [
    r'\d{3,4}p',                   # Resolutions
    r'\bH?\.?264\b', r'\bHEVC\b', r'\bx265\b',  # Codecs
    r'\bWEB[- ]?DL\b', r'\bHDRip\b', r'\bBluRay\b',  # Formats
    r'\bDDP?\d\.\d\b', r'\bAAC\b', r'\bAC3\b',  # Audio formats
    r'\bNF\b', r'\bAMZN\b', r'\bHotstar\b',  # OTT platforms
    r'\bESub\b', r'\bHQ\b', r'\bORG\b',  # Miscellaneous
    r'\bS\d{1,2}\b',                # Season indicators
    r'\bSeason\s?\d{1,2}\b',        # Season indicators
    r'\b\d{4}\b',                   # Years
    r'\.mkv$', r'\.mp4$', r'\.avi$', # File extensions
    r'[-_]\s*x264\b',               # Specific codec pattern
    r'[-_]\s*(Tam|Tel|Hin|Eng)\b',  # Language abbreviations
    r'[-_]\s*[A-Za-z]\s*$',         # Trailing single letters
    r'^\W+|\W+$',                   # Leading/trailing non-word chars
    r'\s*[-_]\s*[-_]\s*',           # Multiple dashes/underscores
]

# ========== GLOBAL DATA ========== #
movie_data: Dict[str, dict] = {}
reaction_counts: Dict[str, dict] = {}
user_reactions: Dict[str, dict] = {}

# ========== HELPER FUNCTIONS ========== #
def generate_movie_id(movie_name: str) -> str:
    """Generate unique movie ID using SHA256"""
    return hashlib.sha256(movie_name.encode()).hexdigest()[:8]

def clean_movie_title(title: str) -> str:
    """
    Clean and normalize movie title by removing all unwanted patterns
    """
    # Remove all unwanted patterns
    for pattern in TITLE_CLEAN_PATTERNS:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)
    
    # Remove special characters except spaces and hyphens
    title = re.sub(r'[^\w\s-]', '', title)
    
    # Remove extra spaces and trim
    title = re.sub(r'\s+', ' ', title).strip()
    
    # Remove leading/trailing dashes and underscores
    title = re.sub(r'^[-_\s]+|[-_\s]+$', '', title)
    
    # Capitalize first letter of each word
    title = title.title()
    
    return title

def extract_year(title: str) -> Tuple[str, Optional[str]]:
    """Extract year from title if present"""
    year_match = re.search(r'\b(19|20)\d{2}\b', title)
    if year_match:
        year = year_match.group(0)
        title = title.replace(year, '').strip()
        return title, year
    return title, None

def quality_sort_key(quality: str) -> int:
    """Sort qualities by resolution"""
    order = {"480p": 1, "720p": 2, "1080p": 3, "2160p": 4, "4k": 5}
    return order.get(quality.lower(), 0)

def build_reaction_buttons(movie_id: str, search_query: str) -> InlineKeyboardMarkup:
    """Dynamically build reaction buttons"""
    buttons = [
        [
            InlineKeyboardButton(f"❤️ {reaction_counts[movie_id]['❤️']}", callback_data=f"h:{movie_id}"),
            InlineKeyboardButton(f"👍 {reaction_counts[movie_id]['👍']}", callback_data=f"l:{movie_id}"),
            InlineKeyboardButton(f"👎 {reaction_counts[movie_id]['👎']}", callback_data=f"d:{movie_id}"),
            InlineKeyboardButton(f"🔥 {reaction_counts[movie_id]['🔥']}", callback_data=f"f:{movie_id}")
        ],
        [
            InlineKeyboardButton('📂 Get File 📂', url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{search_query}')
        ],
        [
            InlineKeyboardButton('♻️ How To Download ♻️', url=HOW_TO_DOWNLOAD_URL)
        ]
    ]
    return InlineKeyboardMarkup(buttons)

# ========== DATA EXTRACTION FUNCTIONS ========== #
async def extract_metadata(text: str) -> Tuple[Set[str], Set[str], Set[str], Set[str]]:
    """Extract all metadata in one pass"""
    text_lower = text.lower()
    formats = set()
    qualities = set()
    languages = set()
    ott = set()

    # Check formats
    format_keywords = {
        "ORG", "HDRip", "WEB-DL", "WEBRip", "HDCAM", "HQ", 
        "CAMRip", "HDTC", "DVDscr", "dvdrip", "dvdscreen", "HDTS"
    }
    for fmt in format_keywords:
        if re.search(rf"\b{re.escape(fmt.lower())}\b", text_lower):
            formats.add(fmt)

    # Check qualities
    quality_keywords = {"480p", "720p", "1080p", "2160p", "4k", "2k"}
    for qual in quality_keywords:
        if re.search(rf"\b{re.escape(qual)}\b", text_lower):
            qualities.add(qual)

    # Check languages
    for lang in CAPTION_LANGUAGES:
        if re.search(rf"\b{re.escape(lang.lower())}\b", text_lower):
            languages.add(lang)

    # Check OTT platforms
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
    for platform, keys in ott_keywords.items():
        if any(re.search(rf"\b{re.escape(k)}\b", text_lower) for k in keys):
            ott.add(platform)

    return formats, qualities, languages, ott

# ========== MOVIE UPDATE HANDLER ========== #
@Client.on_message(filters.chat(CHANNELS) & (filters.document | filters.video | filters.audio))
async def media_handler(bot: Client, message):
    """Handle new media updates from channels"""
    try:
        media = message.document or message.video or message.audio
        if not media:
            return

        # Add custom attributes to media object
        media.file_type = "document" if message.document else "video" if message.video else "audio"
        media.caption = message.caption or ""
        media.file_name = getattr(media, "file_name", "") or ""
        
        success, _ = await save_file(media)
        if not success or not await get_status(bot.me.id):
            return
            
        await process_movie_update(bot, media.file_name, media.caption)
    except Exception as e:
        print(f"❌ Media handler error: {e}")

async def process_movie_update(bot: Client, file_name: str, caption: str):
    """Process and update movie information"""
    try:
        # Clean and normalize movie title
        clean_name = clean_movie_title(file_name)
        clean_name, year = extract_year(clean_name)
        
        # If we have a messy title, try cleaning again with caption
        if not clean_name or len(clean_name) < 3:
            clean_name = clean_movie_title(caption)
            clean_name, year = extract_year(clean_name)
            
        if not clean_name or len(clean_name) < 3:
            print(f"⚠️ Invalid title: {file_name}")
            return

        # Generate unique movie ID
        movie_id = generate_movie_id(clean_name)
        search_query = hashlib.md5(clean_name.encode()).hexdigest()[:12]
        
        # Extract metadata in single pass
        formats, qualities, languages, ott = await extract_metadata(f"{clean_name} {caption}")
        
        # Initialize movie data
        if movie_id not in movie_data:
            movie_data[movie_id] = {
                'title': clean_name,
                'year': year,
                'formats': set(),
                'qualities': set(),
                'languages': set(),
                'ott': set(),
                'message_id': None,
                'search_query': search_query
            }
            reaction_counts[movie_id] = {"❤️": 0, "👍": 0, "👎": 0, "🔥": 0}
            user_reactions[movie_id] = {}
        
        # Update metadata
        movie_data[movie_id]['formats'].update(formats)
        movie_data[movie_id]['qualities'].update(qualities)
        movie_data[movie_id]['languages'].update(languages)
        movie_data[movie_id]['ott'].update(ott)
        
        # Get IMDb details using clean title
        imdb_data = {}
        try:
            imdb_data = await get_poster(clean_name) or {}
        except Exception as e:
            print(f"❌ IMDb fetch error: {e}")
        
        # Build display title with year if available
        display_title = clean_name
        if year:
            display_title = f"{clean_name} ({year})"
        elif imdb_data.get("year"):
            display_title = f"{clean_name} ({imdb_data['year']})"
        
        # Build caption
        caption_lines = [f"<b>【{display_title}】🆕️</b>", ""]
        
        if ott_str := ", ".join(sorted(movie_data[movie_id]['ott'])): 
            caption_lines.append(f"<b>📀 OTT - {ott_str}</b>")
        
        if rating := imdb_data.get("rating"):
            # Ensure rating ends with ★
            rating = rating if '★' in rating else f"{rating}★"
            caption_lines.append(f"<b>⭐️ Rating - {rating}</b>")
        
        if format_str := ", ".join(sorted(movie_data[movie_id]['formats'])): 
            caption_lines.append(f"<b>📺 Format - {format_str}</b>")
        
        if quality_str := ", ".join(sorted(movie_data[movie_id]['qualities'], key=quality_sort_key)):
            caption_lines.append(f"<b>🔰 Quality - {quality_str}</b>")
        
        if language_str := ", ".join(sorted(movie_data[movie_id]['languages'])): 
            caption_lines.append(f"<b>🔈 Audio - {language_str}</b>")
        
        if genres := imdb_data.get("genres"):
            caption_lines.append(f"<b>🎭 Genres - {genres}</b>")
        
        caption_lines.extend(["", f"<blockquote>👑 Provided By : {PROVIDER_NAME}</blockquote>"])
        full_caption = "\n".join(caption_lines)
        
        # Create buttons
        buttons = build_reaction_buttons(movie_id, search_query)
        
        # Edit existing message
        if msg_id := movie_data[movie_id].get('message_id'):
            try:
                await bot.edit_message_caption(
                    chat_id=MOVIE_UPDATE_CHANNEL,
                    message_id=msg_id,
                    caption=full_caption,
                    reply_markup=buttons
                )
                print(f"✅ Updated: {display_title}")
                return
            except MessageNotModified:
                pass  # No changes needed
            except Exception as e:
                print(f"⚠️ Edit failed: {e}")
                movie_data[movie_id]['message_id'] = None  # Reset if edit fails
        
        # Send new message
        poster_title = imdb_data.get("title", clean_name)
        poster_year = imdb_data.get("year", year)
        poster = await fetch_movie_poster(poster_title, poster_year)
        
        try:
            if poster:
                sent = await bot.send_photo(
                    chat_id=MOVIE_UPDATE_CHANNEL,
                    photo=io.BytesIO(poster),
                    caption=full_caption,
                    reply_markup=buttons
                )
            else:
                sent = await bot.send_photo(
                    chat_id=MOVIE_UPDATE_CHANNEL,
                    photo=DEFAULT_POSTER_URL,
                    caption=full_caption,
                    reply_markup=buttons
                )
            
            movie_data[movie_id]['message_id'] = sent.id
            print(f"📤 New movie: {display_title}")
        except Exception as e:
            print(f"❌ Message sending error: {e}")
            
    except Exception as e:
        print(f"❌ Movie update error: {e}")

# ========== REACTION HANDLER ========== #
@Client.on_callback_query(filters.regex(r"^(h|l|d|f):"))
async def reaction_handler(client, query):
    """Handle reaction button clicks"""
    try:
        # Parse callback data
        reaction_code, movie_id = query.data.split(":", 1)
        
        # Validate movie ID
        if movie_id not in reaction_counts:
            await query.answer("⚠️ Movie not found!", show_alert=True)
            return
        
        # Map codes to emojis
        emoji_map = {"h": "❤️", "l": "👍", "d": "👎", "f": "🔥"}
        new_emoji = emoji_map.get(reaction_code)
        if not new_emoji:
            return
        
        user_id = query.from_user.id
        current_reaction = user_reactions[movie_id].get(user_id)
        
        # Update counters
        if current_reaction:
            reaction_counts[movie_id][current_reaction] -= 1
            
        reaction_counts[movie_id][new_emoji] += 1
        user_reactions[movie_id][user_id] = new_emoji
        
        # Update message buttons
        await query.message.edit_reply_markup(
            reply_markup=build_reaction_buttons(
                movie_id, 
                movie_data[movie_id]["search_query"]
            )
        )
        await query.answer(f"✅ {new_emoji} reaction updated!")
        
    except Exception as e:
        print(f"❌ Reaction error: {e}")
        await query.answer("⚠️ Error! Please try later", show_alert=True)

# ========== POSTER FUNCTIONS ========== #
async def fetch_movie_poster(title: str, year: Optional[str] = None) -> Optional[bytes]:
    """Fetch movie poster image with better error handling"""
    if not title:
        return None
        
    try:
        params = {"title": title.strip()}
        if year:
            params["year"] = str(year)
            
        async with aiohttp.ClientSession() as session:
            async with session.get(POSTER_API_URL, params=params, timeout=15) as response:
                if response.status == 200:
                    return await response.read()
                print(f"⚠️ Poster API error: HTTP {response.status}")
    except Exception as e:
        print(f"🌐 Network error: {type(e).__name__}")
    return None
