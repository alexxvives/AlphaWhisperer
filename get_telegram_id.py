#!/usr/bin/env python3
"""
Get your Telegram Chat ID

Run this script, then send any message to your bot.
The script will show your chat_id.
"""

import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def get_chat_id():
    from telegram import Bot
    
    bot = Bot(token=TOKEN)
    
    print("=" * 60)
    print("Getting your Telegram Chat ID...")
    print("=" * 60)
    print()
    print("Instructions:")
    print("1. Open Telegram")
    print("2. Search for your bot and send /start")
    print("3. Send any message to your bot")
    print("4. This script will show your chat_id")
    print()
    print("Checking for messages...")
    print()
    
    try:
        updates = await bot.get_updates()
        
        if not updates:
            print("❌ No messages found!")
            print()
            print("Please:")
            print("1. Search for your bot in Telegram")
            print("2. Send /start")
            print("3. Send any message")
            print("4. Run this script again")
            return
        
        # Collect all unique chats (both individual and groups)
        chats = {}
        for update in updates:
            if update.message:
                chat = update.message.chat
                chat_id = chat.id
                
                if chat_id not in chats:
                    chat_type = chat.type
                    if chat_type == "private":
                        chats[chat_id] = {
                            "type": "Personal Chat",
                            "name": f"{update.message.from_user.first_name or 'N/A'}",
                            "username": f"@{update.message.from_user.username}" if update.message.from_user.username else "N/A"
                        }
                    elif chat_type in ["group", "supergroup"]:
                        chats[chat_id] = {
                            "type": "Group",
                            "name": chat.title or "N/A",
                            "username": f"@{chat.username}" if chat.username else "N/A"
                        }
        
        if chats:
            print("✅ Found chats:")
            print()
            for chat_id, info in chats.items():
                print(f"Type: {info['type']}")
                print(f"Chat ID: {chat_id}")
                print(f"Name: {info['name']}")
                print(f"Username: {info['username']}")
                print("-" * 60)
            print()
            print("=" * 60)
            print("Copy the chat ID you want to your .env file:")
            print("=" * 60)
            print("TELEGRAM_CHAT_ID=<your_chosen_chat_id>")
            print()
        else:
            print("❌ No chats found!")
            print()
            print("Please:")
            print("1. Search for your bot in Telegram")
            print("2. Send /start")
            print("3. Send any message")
            print("4. Run this script again")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        print()
        print("Make sure:")
        print("1. Your bot token is correct in .env")
        print("2. You've sent a message to your bot")

if __name__ == "__main__":
    asyncio.run(get_chat_id())
