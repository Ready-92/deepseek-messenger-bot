"""
Messenger Bot - DeepSeek AI tích hợp Facebook Messenger
Xử lý Webhook + Gọi DeepSeek API trả lời tin nhắn
"""
import json
import hmac
import hashlib
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Request, HTTPException, Query

from config import (
    MESSENGER_VERIFY_TOKEN,
    MESSENGER_PAGE_ACCESS_TOKEN,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    MODEL_NAME,
)

router = APIRouter(prefix="/messenger", tags=["Messenger Bot"])

# Base URL cho Facebook Graph API
GRAPH_API = "https://graph.facebook.com/v19.0"

# In-memory lưu context hội thoại mỗi user (PSID -> list messages)
# Trong production nên dùng Redis / DB
conversations: dict[str, list[dict]] = {}

# System prompt mặc định cho bot
SYSTEM_PROMPT = (
    "Bạn là trợ lý AI thông minh chạy trên Messenger, sử dụng DeepSeek API. "
    "Trả lời bằng tiếng Việt, thân thiện, chuyên nghiệp. "
    "Hỗ trợ tư vấn công việc, giải đáp thắc mắc, viết nội dung, lập trình, v.v. "
    "Nếu câu hỏi không rõ ràng, hãy hỏi lại để làm rõ. "
    "Trả lời ngắn gọn, súc tích, dễ hiểu trên giao diện chat."
)

# Lịch sử hội thoại tối đa lưu giữ (số cặp user+assistant)
MAX_HISTORY = 10


# ==============================================
# Helpers
# ==============================================

def verify_signature(payload: bytes, signature: str, app_secret: str) -> bool:
    """Xác thực request từ Facebook bằng HMAC-SHA1."""
    if not app_secret:
        return True  # skip nếu không có app secret
    expected = hmac.new(
        app_secret.encode(), payload, hashlib.sha1
    ).hexdigest()
    return hmac.compare_digest(f"sha1={expected}", signature)


async def send_message(psid: str, text: str) -> dict:
    """Gửi tin nhắn text tới user qua Messenger Send API."""
    url = f"{GRAPH_API}/me/messages"
    params = {"access_token": MESSENGER_PAGE_ACCESS_TOKEN}
    body = {
        "recipient": {"id": psid},
        "message": {"text": text},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, params=params, json=body)
        return resp.json()


async def send_typing(psid: str, on: bool = True):
    """Bật/tắt typing indicator."""
    url = f"{GRAPH_API}/me/messages"
    params = {"access_token": MESSENGER_PAGE_ACCESS_TOKEN}
    action = "typing_on" if on else "typing_off"
    body = {"recipient": {"id": psid}, "sender_action": action}
    async with httpx.AsyncClient(timeout=30) as client:
        await client.post(url, params=params, json=body)


async def get_user_info(psid: str) -> dict:
    """Lấy tên + avatar của user từ PSID."""
    url = f"{GRAPH_API}/{psid}"
    params = {
        "fields": "first_name,last_name,profile_pic",
        "access_token": MESSENGER_PAGE_ACCESS_TOKEN,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        return resp.json() if resp.status_code == 200 else {}


def split_long_message(text: str, limit: int = 2000) -> list[str]:
    """Cắt tin nhắn dài thành nhiều phần <= limit ký tự."""
    if len(text) <= limit:
        return [text]

    # Ưu tiên cắt tại dòng mới
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


def get_or_create_context(psid: str) -> list[dict]:
    """Lấy hoặc khởi tạo context cho user."""
    if psid not in conversations:
        conversations[psid] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return conversations[psid]


# ==============================================
# DeepSeek API Call
# ==============================================

async def call_deepseek(psid: str, user_message: str) -> str:
    """Gọi DeepSeek API (non-streaming) và trả về text response."""
    if not DEEPSEEK_API_KEY:
        return "⚠️ Bot chưa được cấu hình API Key. Vui lòng liên hệ admin."

    context = get_or_create_context(psid)
    context.append({"role": "user", "content": user_message})

    # Giới hạn lịch sử
    system_msg = context[0]  # system prompt
    recent = context[1:]  # bỏ system prompt
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
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            if resp.status_code != 200:
                error_text = resp.text[:300]
                return f"❌ Lỗi DeepSeek API ({resp.status_code}): {error_text}"

            data = resp.json()
            reply = data["choices"][0]["message"]["content"]

        # Lưu vào context
        context.append({"role": "assistant", "content": reply})

        # Trim nếu quá dài
        if len(context) > (MAX_HISTORY * 2) + 2:
            # Giữ system prompt + recent
            conversations[psid] = [system_msg] + context[-(MAX_HISTORY * 2):]

        return reply

    except httpx.TimeoutException:
        return "⏰ DeepSeek API quá thời gian phản hồi. Vui lòng thử lại sau."
    except Exception as e:
        return f"❌ Lỗi không xác định: {str(e)[:200]}"


# ==============================================
# Xử lý tin nhắn
# ==============================================

async def process_message(psid: str, message: dict) -> None:
    """Xử lý 1 tin nhắn từ user."""
    text = message.get("text", "").strip()
    if not text:
        return

    print(f"[Messenger] Tin nhắn từ {psid}: {text[:100]}")

    # Typing indicator
    await send_typing(psid, on=True)

    # Xử lý các lệnh đặc biệt
    if text.lower() in ["/reset", "/xóa", "/clear", "/mới"]:
        if psid in conversations:
            conversations[psid] = [{"role": "system", "content": SYSTEM_PROMPT}]
        await send_message(psid, "✅ Đã xóa lịch sử hội thoại. Bắt đầu cuộc trò chuyện mới!")
        await send_typing(psid, on=False)
        return

    if text.lower() in ["/help", "/giúp", "/trợ giúp"]:
        help_text = (
            "🤖 **DeepSeek AI Bot**\n\n"
            "Tôi là trợ lý AI hỗ trợ:\n"
            "• Tư vấn công việc\n"
            "• Giải đáp thắc mắc\n"
            "• Viết nội dung, email, báo cáo\n"
            "• Hỗ trợ lập trình\n"
            "• Và nhiều hơn nữa!\n\n"
            "📌 **Lệnh:**\n"
            "/reset - Xóa lịch sử chat\n"
            "/help  - Hiển thị trợ giúp\n\n"
            "💬 Cứ nhắn câu hỏi, tôi sẽ trả lời!"
        )
        await send_message(psid, help_text)
        await send_typing(psid, on=False)
        return

    # Gọi DeepSeek
    reply = await call_deepseek(psid, text)

    # Gửi phản hồi (tự động cắt nếu dài)
    chunks = split_long_message(reply)
    for i, chunk in enumerate(chunks):
        await send_message(psid, f"{chunk}" if len(chunks) == 1 else f"📄 ({i+1}/{len(chunks)})\n{chunk}")
        if i < len(chunks) - 1:
            await send_typing(psid, on=True)
            time.sleep(0.5)

    await send_typing(psid, on=False)


async def process_attachments(psid: str, attachments: list[dict]) -> None:
    """Xử lý attachments (ảnh, file, v.v.) - hiện chỉ thông báo."""
    for att in attachments:
        att_type = att.get("type", "unknown")
        if att_type == "image":
            await send_message(psid, "🖼️ Bot hiện chưa hỗ trợ xử lý ảnh. Vui lòng gửi nội dung bằng text.")
        elif att_type == "file":
            await send_message(psid, "📎 Bot hiện chưa hỗ trợ xử lý file. Vui lòng gửi nội dung bằng text.")
        else:
            await send_message(psid, f"⚠️ Bot chưa hỗ trợ định dạng `{att_type}`.")


# ==============================================
# Webhook Endpoints
# ==============================================

@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
):
    """Xác thực webhook từ Facebook (GET request)."""
    if hub_mode == "subscribe" and hub_verify_token == MESSENGER_VERIFY_TOKEN:
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Token xác thực không đúng")


@router.post("/webhook")
async def receive_webhook(request: Request):
    """Nhận sự kiện từ Messenger (POST request)."""
    body = await request.body()

    # Tùy chọn: Verify signature nếu có APP_SECRET
    # signature = request.headers.get("X-Hub-Signature", "")
    # if MESSENGER_APP_SECRET and not verify_signature(body, signature, MESSENGER_APP_SECRET):
    #     raise HTTPException(status_code=403, detail="Chữ ký không hợp lệ")

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Xử lý từng entry
    for entry in data.get("entry", []):
        for event in entry.get("messaging", []):
            sender_id = event.get("sender", {}).get("id")
            if not sender_id:
                continue

            # Chỉ xử lý tin nhắn từ user (bỏ qua echo, delivery, read)
            if "message" not in event:
                continue
            if event["message"].get("is_echo", False):
                continue

            msg = event["message"]

            # Xử lý text message
            if "text" in msg:
                await process_message(sender_id, msg)

            # Xử lý attachments
            if "attachments" in msg:
                await process_attachments(sender_id, msg["attachments"])

    return {"status": "ok"}
