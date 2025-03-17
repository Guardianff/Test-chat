import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Configuration
import os
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_ID")    # For receiving reports
active_conversations = {}
message_sender_map = {}  # Stores {(chat_id, message_id): sender_id}

# States
WAITING, CHATTING = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Notify admin when new user starts the bot"""
    user = update.effective_user
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"🚀 New user started bot: {user.id} (@{user.username})"
    )
    await update.message.reply_text(
        f"👋 Welcome {user.first_name}!\n\n"
        "📌 Commands:\n"
        "/start - Show menu\n"
        "/stop - End chat\n"
        "/chat - Find partner\n"
        "/report - Report message (reply to message)",
        reply_markup=ReplyKeyboardRemove()
    )


    # Add this missing function
async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Match users anonymously"""
    user_id = update.effective_user.id
    
    if user_id in active_conversations:
        await update.message.reply_text("⚠️ You're already in a conversation!")
        return
    
    # Find available partner
    for uid in active_conversations:
        if active_conversations[uid] is None:
            active_conversations[uid] = user_id
            active_conversations[user_id] = uid
            
            # Notify both users
            await context.bot.send_message(
                chat_id=uid,
                text="🔗 Connected to anonymous partner!\nSend /stop to end chat."
            )
            await context.bot.send_message(
                chat_id=user_id,
                text="🔗 Connected to anonymous partner!\nSend /stop to end chat."
            )
            return
    
    # If no partner found
    active_conversations[user_id] = None
    await update.message.reply_text("🔎 Searching for partner...")

# Add these other required functions if missing
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """End current conversation"""
    user_id = update.effective_user.id
    if user_id in active_conversations:
        partner_id = active_conversations[user_id]
        del active_conversations[user_id]
        del active_conversations[partner_id]
        
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Conversation ended. Use /chat to start new one."
        )
        await context.bot.send_message(
            chat_id=partner_id,
            text="❌ Partner ended the conversation. Use /chat to find new one."
        )
    return ConversationHandler.END

async def report_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle message reporting"""
    reporter = update.effective_user
    replied_msg = update.message.reply_to_message

    if not replied_msg:
        await update.message.reply_text("⚠️ Reply to a message to report it!")
        return

    # Get original sender from message map
    msg_key = (replied_msg.chat_id, replied_msg.message_id)
    original_sender = message_sender_map.get(msg_key)

    if not original_sender:
        await update.message.reply_text("❌ Message not found in history")
        return

    # Send report to admin
    report_details = (
        f"🚨 New Report!\n\n"
        f"Reporter: {reporter.id}\n"
        f"Reported User: {original_sender}\n"
        f"Message: {replied_msg.text or 'MEDIA CONTENT'}\n"
        f"Message ID: {msg_key[1]}"
    )
    
    try:
        # Forward original message to admin
        await replied_msg.forward(ADMIN_CHAT_ID)
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=report_details
        )
        await update.message.reply_text("✅ Report sent to admin!")
    except Exception as e:
        logging.error(f"Report failed: {e}")
        await update.message.reply_text("❌ Failed to send report")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forward messages and track origins"""
    user_id = update.effective_user.id
    partner_id = active_conversations.get(user_id)
    
    if not partner_id:
        await update.message.reply_text("⚠️ Start a chat with /chat first")
        return

    try:
        # Store message origin before forwarding
        forward_methods = {
            'text': context.bot.send_message,
            'photo': context.bot.send_photo,
            'video': context.bot.send_video,
            'document': context.bot.send_document,
            'audio': context.bot.send_audio
        }

        for msg_type, method in forward_methods.items():
            if getattr(update.message, msg_type, None):
                sent_msg = await method(
                    chat_id=partner_id,
                    **{msg_type: getattr(update.message, msg_type)},
                    caption=f"👤 Anonymous: {update.message.caption}" if update.message.caption else None
                )
                # Track message origin
                message_sender_map[(partner_id, sent_msg.message_id)] = user_id
                break

    except Exception as e:
        logging.error(f"Forward error: {e}")
        await update.message.reply_text("❌ Failed to send message")

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('chat', find_partner)],
        states={
            WAITING: [MessageHandler(filters.TEXT & ~filters.COMMAND, find_partner)],
            CHATTING: [
                MessageHandler(
                    filters.TEXT | filters.PHOTO | filters.VIDEO | 
                    filters.DOCUMENT | filters.AUDIO,
                    handle_message
                )
            ]
        },
        fallbacks=[CommandHandler('stop', stop)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("report", report_message))

    app.run_polling()

if __name__ == "__main__":
    main()
