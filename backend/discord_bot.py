"""
Discord Bot - DeepSeek AI tích hợp Discord
Slash commands + Prefix commands + DM support
"""
import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands
import httpx

from config import (
    DISCORD_BOT_TOKEN,
    DISCORD_COMMAND_PREFIX,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    MODEL_NAME,
)

log = logging.getLogger("discord_bot")

# ==============================================
# Conversation Context (per channel/DM)
# key: discord_channel_id -> list[dict]
# ==============================================
conversations: dict[int, list[dict]] = {}

SYSTEM_PROMPT = (
    "Bạn là DeepSeek V4 Pro, trợ lý AI trên Discord. "
    "Trả lời bằng tiếng Việt, thân thiện, chuyên nghiệp. "
    "Hỗ trợ tư vấn, giải đáp, viết code, viết nội dung. "
    "Trả lời ngắn gọn, súc tích. Dùng Markdown của Discord khi cần."
)

MAX_HISTORY = 10  # số cặp user+assistant tối đa lưu


def get_context(channel_id: int) -> list[dict]:
    """Lấy hoặc khởi tạo context cho channel."""
    if channel_id not in conversations:
        conversations[channel_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return conversations[channel_id]


def reset_context(channel_id: int):
    conversations[channel_id] = [{"role": "system", "content": SYSTEM_PROMPT}]


# ==============================================
# DeepSeek API Call
# ==============================================
async def call_deepseek(channel_id: int, user_message: str) -> str:
    """Gọi DeepSeek API và trả về text."""
    if not DEEPSEEK_API_KEY:
        return "⚠️ Bot chưa cấu hình API Key."

    context = get_context(channel_id)
    context.append({"role": "user", "content": user_message})

    system_msg = context[0]
    recent = context[1:]
    if len(recent) > MAX_HISTORY * 2:
        recent = recent[-(MAX_HISTORY * 2):]
    messages = [system_msg] + recent

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "temperature": 0.7,
        "max_tokens": 2048,
        "top_p": 0.9,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            if resp.status_code != 200:
                err = resp.text[:300]
                return f"❌ Lỗi API ({resp.status_code}): {err}"

            data = resp.json()
            reply = data["choices"][0]["message"]["content"]

        context.append({"role": "assistant", "content": reply})

        if len(context) > (MAX_HISTORY * 2) + 2:
            conversations[channel_id] = [system_msg] + context[-(MAX_HISTORY * 2):]

        return reply

    except httpx.TimeoutException:
        return "⏰ DeepSeek API timeout. Thử lại sau."
    except Exception as e:
        return f"❌ Lỗi: {str(e)[:200]}"


# ==============================================
# Split long message into Discord-safe chunks
# ==============================================
def split_message(text: str, limit: int = 1900) -> list[str]:
    """Cắt tin nhắn dài thành chunks <= limit."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = text.rfind(" ", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks


# ==============================================
# Discord Bot Class
# ==============================================
class DeepSeekBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents, command_prefix=DISCORD_COMMAND_PREFIX)
        self.tree = app_commands.CommandTree(self)
        self._ready = asyncio.Event()

    async def setup_hook(self):
        """Đăng ký slash commands."""
        # /chat
        @self.tree.command(name="chat", description="Chat với DeepSeek AI")
        @app_commands.describe(message="Nội dung tin nhắn")
        async def chat_cmd(interaction: discord.Interaction, message: str):
            await handle_slash_chat(interaction, message)

        # /reset
        @self.tree.command(name="reset", description="Xóa lịch sử hội thoại với bot")
        async def reset_cmd(interaction: discord.Interaction):
            reset_context(interaction.channel_id)
            await interaction.response.send_message(
                "✅ Đã xóa lịch sử hội thoại kênh này!", ephemeral=True
            )

        # /help
        @self.tree.command(name="help", description="Hiển thị trợ giúp")
        async def help_cmd(interaction: discord.Interaction):
            embed = discord.Embed(
                title="🤖 DeepSeek AI Bot - Trợ giúp",
                description="Trợ lý AI thông minh trên Discord, dùng DeepSeek API.",
                color=0x5865F2,
            )
            embed.add_field(
                name="📌 Slash Commands",
                value=(
                    "`/chat <nội dung>` - Chat với AI\n"
                    "`/reset` - Xóa lịch sử hội thoại kênh\n"
                    "`/help` - Hiển thị trợ giúp này\n"
                ),
                inline=False,
            )
            embed.add_field(
                name="💬 Cách dùng",
                value=(
                    "- **DM trực tiếp**: Nhắn tin riêng với bot\n"
                    "- **Kênh server**: @mention bot hoặc reply tin nhắn của bot\n"
                    f"- **Prefix command**: `{DISCORD_COMMAND_PREFIX}chat <nội dung>`\n"
                ),
                inline=False,
            )
            embed.set_footer(text="Powered by DeepSeek API")
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # Sync commands
        await self.tree.sync()
        log.info("Slash commands synced.")

    async def on_ready(self):
        log.info(f"Discord Bot online: {self.user} (ID: {self.user.id})")
        self._ready.set()


# ==============================================
# Slash command handler
# ==============================================
async def handle_slash_chat(interaction: discord.Interaction, message: str):
    """Xử lý /chat slash command."""
    await interaction.response.defer()  # typing indicator

    reply = await call_deepseek(interaction.channel_id, message)
    chunks = split_message(reply)

    await interaction.followup.send(chunks[0])
    for chunk in chunks[1:]:
        await interaction.channel.send(chunk)


# ==============================================
# Message handler
# ==============================================
async def handle_message(bot: DeepSeekBot, message: discord.Message):
    """Xử lý tin nhắn thông thường."""
    # Bỏ qua tin nhắn của chính bot
    if message.author.id == bot.user.id:
        return

    content = message.content.strip()
    if not content:
        return

    channel_id = message.channel.id

    # Prefix commands trong DM và kênh
    prefix = DISCORD_COMMAND_PREFIX
    if content.startswith(prefix):
        cmd = content[len(prefix):].strip()
        await handle_prefix_command(message, cmd, channel_id)
        return

    # DM: luôn trả lời
    if isinstance(message.channel, discord.DMChannel):
        await handle_dm_message(bot, message, content, channel_id)
        return

    # Server channel: trả lời ngay công khai
    # Xóa @mention bot nếu có
    if bot.user in message.mentions:
        content = content.replace(f"<@{bot.user.id}>", "").strip()
        if not content:
            await message.reply("👋 Chào! Gửi câu hỏi để chat với tôi.")
            return

    async with message.channel.typing():
        reply = await call_deepseek(channel_id, content)
        chunks = split_message(reply)
        await message.reply(chunks[0])
        for chunk in chunks[1:]:
            await message.channel.send(chunk)


async def handle_server_message(bot: DeepSeekBot, message: discord.Message, content: str, channel_id: int):
    """DEPRECATED - không dùng nữa"""
    pass


async def handle_dm_message(bot, message, content, channel_id):
    """Xử lý DM."""
    async with message.channel.typing():
        reply = await call_deepseek(channel_id, content)
        chunks = split_message(reply)
        await message.channel.send(chunks[0])
        for chunk in chunks[1:]:
            await message.channel.send(chunk)


async def handle_prefix_command(message: discord.Message, cmd: str, channel_id: int):
    """Xử lý prefix command (!chat, !reset, !help)."""
    if cmd.lower().startswith("chat "):
        text = cmd[5:].strip()
        if not text:
            await message.reply("❗ Dùng: `!chat <nội dung>`")
            return
        async with message.channel.typing():
            reply = await call_deepseek(channel_id, text)
            chunks = split_message(reply)
            await message.reply(chunks[0])
            for chunk in chunks[1:]:
                await message.channel.send(chunk)

    elif cmd.lower() in ("reset", "xóa", "clear", "mới"):
        reset_context(channel_id)
        await message.reply("✅ Đã xóa lịch sử hội thoại!")

    elif cmd.lower() in ("help", "giúp"):
        prefix = DISCORD_COMMAND_PREFIX
        help_text = (
            "🤖 **DeepSeek AI Bot**\n\n"
            f"`{prefix}chat <nội dung>` - Chat với AI\n"
            f"`{prefix}reset` - Xóa lịch sử hội thoại\n"
            f"`{prefix}help` - Hiển thị trợ giúp\n\n"
            "💬 DM trực tiếp hoặc @mention bot trong kênh."
        )
        await message.reply(help_text)

    else:
        # Unknown prefix cmd -> coi như chat
        async with message.channel.typing():
            reply = await call_deepseek(channel_id, cmd)
            chunks = split_message(reply)
            await message.reply(chunks[0])
            for chunk in chunks[1:]:
                await message.channel.send(chunk)


# ==============================================
# Bot runner (called from main.py startup)
# ==============================================
_bot_instance: Optional[DeepSeekBot] = None


def get_bot() -> Optional[DeepSeekBot]:
    return _bot_instance


async def start_discord_bot():
    """Khởi động Discord bot (chạy trong background task)."""
    global _bot_instance
    if not DISCORD_BOT_TOKEN:
        log.warning("DISCORD_BOT_TOKEN chưa cấu hình. Discord bot không khởi động.")
        return

    _bot_instance = DeepSeekBot()

    # Register event handlers
    @_bot_instance.event
    async def on_message(message: discord.Message):
        await handle_message(_bot_instance, message)

    log.info("Starting Discord bot...")
    try:
        await _bot_instance.start(DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        log.error("Discord bot: Token không hợp lệ.")
    except Exception as e:
        log.error(f"Discord bot lỗi: {e}")


async def stop_discord_bot():
    """Dừng Discord bot."""
    global _bot_instance
    if _bot_instance and not _bot_instance.is_closed():
        await _bot_instance.close()
        log.info("Discord bot stopped.")
