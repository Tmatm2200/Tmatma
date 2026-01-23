"""
Admin-only commands for bot configuration.
"""
from telegram import Update
from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes
from utils.database import Database
from utils.decorators import owner_only, handle_errors


@owner_only
@handle_errors
async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /promote - promote a user to admin with a custom title.
    Usage: /promote @user Title or reply with /promote Title
    """
    chat_id = str(update.effective_chat.id)
    args = context.args
    message = update.message
    
    target_user = None
    custom_title = "Admin"
    
    # Check if reply
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        if args:
            custom_title = " ".join(args)
    # Check if mention
    elif args:
        # Try to get user from entities if mentioned
        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    # Remove the mention from args to get title
                    # This is tricky with args list, better to rely on args logic
                    break
                elif entity.type == "mention":
                    # We have a username in args[0]
                    username = args[0]
                    # We can't easily resolve username to user object without a chat member lookup
                    # But we can try to find the user in the chat
                    try:
                        # This might fail if user is not in chat or bot hasn't seen them
                        # But for now let's assume we need to handle it or ask for reply
                        pass 
                    except Exception:
                        pass
        
        # If we still don't have a user, try to resolve from args[0] if it looks like a username
        if not target_user and args[0].startswith("@"):
            try:
                username = args[0]
                user_id = await Database.get_user_id_by_username(username)
                if user_id:
                    member = await context.bot.get_chat_member(chat_id, int(user_id))
                    target_user = member.user
            except Exception:
                pass
                
        if not target_user:
             # If we couldn't resolve from entity, maybe it's a raw ID?
            if args[0].isdigit():
                try:
                    target_user = await context.bot.get_chat_member(chat_id, int(args[0]))
                    target_user = target_user.user
                except Exception:
                    pass

        if target_user:
            if len(args) > 1:
                custom_title = " ".join(args[1:])
            elif message.reply_to_message:
                 # If we found user from args but it was a reply? Logic overlap.
                 # If reply, we took target from reply.
                 pass
            else:
                # If we found user from args[0], title is args[1:]
                custom_title = " ".join(args[1:]) if len(args) > 1 else "Admin"

    if not target_user:
        await message.reply_text("❌ Please reply to a user or mention them to promote.")
        return

    if target_user.is_bot:
        # The prompt says "give an admin to user or bot"
        pass

    try:
        # Promote the user
        # Note: Bot needs 'can_promote_members' permission
        await context.bot.promote_chat_member(
            chat_id=chat_id,
            user_id=target_user.id,
            can_manage_chat=True,
            can_delete_messages=True,
            can_invite_users=True,
            can_restrict_members=True,
            can_pin_messages=True,
            can_promote_members=False,
            is_anonymous=False,
            can_manage_video_chats=True
        )
        
        # Set custom title
        # Note: Custom title max length is 16 chars
        if len(custom_title) > 16:
            custom_title = custom_title[:16]
            
        await context.bot.set_chat_administrator_custom_title(
            chat_id=chat_id,
            user_id=target_user.id,
            custom_title=custom_title
        )
        
        # Record in database
        await Database.add_bot_promoted_admin(chat_id, str(target_user.id), custom_title)
        
        await message.reply_text(f"✅ Promoted {target_user.mention_html()} to admin with title '{custom_title}'.", parse_mode='HTML')
        
    except Exception as e:
        await message.reply_text(f"❌ Failed to promote: {str(e)}")


@owner_only
@handle_errors
async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /kick - kick a user.
    Can kick admins ONLY if they were promoted by this bot.
    Usage: /kick @user or reply with /kick
    """
    chat_id = str(update.effective_chat.id)
    args = context.args
    message = update.message
    
    target_user = None
    
    # Check if reply
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
    # Check if mention/args
    elif args:
        if args[0].isdigit():
             try:
                member = await context.bot.get_chat_member(chat_id, int(args[0]))
                target_user = member.user
             except:
                 pass
        else:
            # Check entities for mention
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    break
            
            # Try username lookup if no entity found
            if not target_user and args[0].startswith("@"):
                try:
                    user_id = await Database.get_user_id_by_username(args[0])
                    if user_id:
                        member = await context.bot.get_chat_member(chat_id, int(user_id))
                        target_user = member.user
                except:
                    pass
    
    if not target_user:
        await message.reply_text("❌ Please reply to a user or mention them to kick.")
        return

    # Check if target is admin
    member = await context.bot.get_chat_member(chat_id, target_user.id)
    is_admin = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    
    if is_admin:
        # Check if promoted by bot
        is_bot_promoted = await Database.is_bot_promoted_admin(chat_id, str(target_user.id))
        if not is_bot_promoted:
            await message.reply_text("❌ I cannot kick this admin (not promoted by me).")
            return
        
        # If promoted by bot, we can try to kick.
        # We should also remove them from DB
        await Database.remove_bot_promoted_admin(chat_id, str(target_user.id))

    try:
        # Ban (Kick)
        await context.bot.ban_chat_member(chat_id, target_user.id)
        # Unban to allow rejoining (standard "kick" behavior)
        await context.bot.unban_chat_member(chat_id, target_user.id)
        
        await message.reply_text(f"✅ Kicked {target_user.mention_html()}.", parse_mode='HTML')
        
    except Exception as e:
        await message.reply_text(f"❌ Failed to kick: {str(e)}")


@owner_only
@handle_errors
async def admins_enable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admins_enable - allow admins to bypass filters."""
    chat_id = str(update.effective_chat.id)
    Database.set_admin_bypass(chat_id, True)
    await update.message.reply_text("✅ Admins can now bypass sticker blocks and word filters.")


@owner_only
@handle_errors
async def admins_disable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admins_disable - make admins follow rules."""
    chat_id = str(update.effective_chat.id)
    Database.set_admin_bypass(chat_id, False)
    await update.message.reply_text("✅ Admins must now follow all rules like regular users.")
