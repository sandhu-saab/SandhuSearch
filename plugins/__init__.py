
from aiohttp import web
from .route import routes
from asyncio import sleep 
from datetime import datetime
from database.users_chats_db import db
from info import LOG_CHANNEL, URL
import aiohttp
import asyncio
import logging

logging.basicConfig(level=logging.INFO)


async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app

async def check_expired_premium(client):
    while 1:
        data = await db.get_expired(datetime.now())
        for user in data:
            user_id = user["id"]
            await db.remove_premium_access(user_id)
            try:
                user = await client.get_users(user_id)
                await client.send_message(
                    chat_id=user_id,
                    text=f"<b>ʜᴇʏ {user.mention},\n\nʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ʜᴀꜱ ʙᴇᴇɴ ᴇxᴘɪʀᴇᴅ. ᴛʜᴀɴᴋꜱ ꜰᴏʀ ᴜꜱɪɴɢ ᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ꜱᴇʀᴠɪᴄᴇ. ɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ʙᴜᴛ ᴀɢᴀɪɴ ᴛʜᴇɴ ꜱᴇɴᴅ /plan</b>"
                )
                await client.send_message(LOG_CHANNEL, text=f"<b>#Premium_Expire\n\nUser name: {user.mention}\nUser id: <code>{user_id}</code>")
            except Exception as e:
                print(e)
            await sleep(0.5)
        await sleep(1)

async def keep_alive():
    """Keep Bot Alive By Sending Periodic Pings In Every 2 Minutes."""
    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(120)
            try:
                async with session.get(URL) as resp:
                    if resp.status != 200:
                        logging.warning(f"⚠️ Ping Error! Status: {resp.status}")
                    else:
                        logging.info("✅ Ping Successful")
            except Exception as e:
                logging.error(f"❌ Ping Failed: {e}")   

