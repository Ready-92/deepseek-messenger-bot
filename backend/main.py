import json
from datetime import datetime, timedelta
from typing import Optional, Any

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import httpx
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from jose import JWTError, jwt

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    MODEL_NAME,
    GOOGLE_CLIENT_ID,
    JWT_SECRET,
    JWT_ALGORITHM,
    VISION_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    MESSENGER_PAGE_ACCESS_TOKEN,
    DISCORD_BOT_TOKEN,
)
from messenger_bot import router as messenger_router
from discord_bot import start_discord_bot, stop_discord_bot

# ===== Lifespan =====
import asyncio
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi động / dừng Discord bot."""
    if DISCORD_BOT_TOKEN:
        asyncio.create_task(start_discord_bot())
    yield
    await stop_discord_bot()

app = FastAPI(title="DeepSeek Chat API", version="2.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Messenger Bot router (chỉ nếu đã cấu hình PAGE_ACCESS_TOKEN)
if MESSENGER_PAGE_ACCESS_TOKEN:
    app.include_router(messenger_router)

security = HTTPBearer(auto_error=False)

# ===== In-memory storage =====
# dict: user_id -> { "id", "email", "name", "avatar", "sessions": [...] }
users_db: dict[str, dict] = {}


# ===== Pydantic Models =====
class ChatMessage(BaseModel):
    role: str
    content: Any  # str hoặc list[dict] cho multimodal (vision)


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    stream: bool = True
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 0.9


class GoogleLoginRequest(BaseModel):
    credential: str  # Google ID token from frontend


class ChatSession(BaseModel):
    id: str
    title: str
    messages: list[dict]


# ===== JWT Helpers =====
def create_jwt(user_id: str, email: str) -> str:
    expire = datetime.utcnow() + timedelta(days=30)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token không hợp lệ hoặc đã hết hạn")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    if credentials is None:
        return None
    payload = decode_jwt(credentials.credentials)
    user_id = payload.get("sub")
    if user_id not in users_db:
        raise HTTPException(status_code=401, detail="Người dùng không tồn tại")
    return users_db[user_id]


# ===== Auth Endpoints =====
@app.post("/api/auth/google")
async def google_login(req: GoogleLoginRequest):
    """Xác thực Google ID token và trả về JWT + user info."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID chưa được cấu hình")

    try:
        id_info = id_token.verify_oauth2_token(
            req.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Google token không hợp lệ")

    google_id = id_info.get("sub")
    email = id_info.get("email", "")
    name = id_info.get("name", email)
    avatar = id_info.get("picture", "")

    # Tìm hoặc tạo user
    user_id = f"google_{google_id}"
    if user_id not in users_db:
        users_db[user_id] = {
            "id": user_id,
            "email": email,
            "name": name,
            "avatar": avatar,
            "sessions": [],
        }
    else:
        # Cập nhật thông tin mới nhất từ Google
        users_db[user_id].update({"email": email, "name": name, "avatar": avatar})

    token = create_jwt(user_id, email)
    return {
        "token": token,
        "user": {
            "id": user_id,
            "email": email,
            "name": name,
            "avatar": avatar,
        },
    }


@app.get("/api/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Lấy thông tin user hiện tại từ JWT."""
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "avatar": user["avatar"],
    }


# ===== Session Endpoints =====
@app.get("/api/sessions")
async def get_sessions(user: dict = Depends(get_current_user)):
    """Lấy tất cả chat sessions của user."""
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    return user.get("sessions", [])


@app.post("/api/sessions")
async def save_sessions(
    sessions: list[ChatSession],
    user: dict = Depends(get_current_user),
):
    """Lưu tất cả chat sessions của user."""
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    user["sessions"] = [s.model_dump() for s in sessions]
    return {"ok": True}


@app.put("/api/sessions/sync")
async def sync_sessions(
    sessions: list[ChatSession],
    user: dict = Depends(get_current_user),
):
    """Đồng bộ sessions từ client lên server."""
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    local_sessions = [s.model_dump() for s in sessions]

    # Merge: server sessions thắng nếu cùng id, local thắng nếu server không có
    server_map = {s["id"]: s for s in user.get("sessions", [])}
    for s in local_sessions:
        server_map[s["id"]] = s  # local ghi đè server
    user["sessions"] = sorted(
        server_map.values(),
        key=lambda s: local_sessions.index(next((ls for ls in local_sessions if ls["id"] == s["id"]), s))
        if any(ls["id"] == s["id"] for ls in local_sessions) else -1,
        reverse=True,
    )
    return {"ok": True, "sessions": user["sessions"]}


# ===== Helpers: detect image in messages =====
def _has_images(messages: list) -> bool:
    for msg in messages:
        if isinstance(msg.content, list):
            for part in msg.content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def _get_vision_config():
    """Trả về (provider, api_key, base_url, model) cho vision."""
    if VISION_PROVIDER == "gemini" and GEMINI_API_KEY:
        return "gemini", GEMINI_API_KEY, "", GEMINI_MODEL
    if OPENAI_API_KEY:
        return "openai", OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
    return None, None, None, None


# ===== Chat Endpoint =====
@app.post("/api/chat")
async def chat(
    req: ChatRequest,
    user: Optional[dict] = Depends(get_current_user),
):
    """Gửi tin nhắn tới DeepSeek API (streaming). Nếu có ảnh -> vision provider."""
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=500, detail="API key chưa được cấu hình")

    msgs = [m.model_dump() for m in req.messages]
    has_images = _has_images(req.messages)

    if has_images:
        provider, api_key, base_url, model = _get_vision_config()
        if not provider or not api_key:
            raise HTTPException(
                status_code=400,
                detail="Không có vision provider nào được cấu hình. "
                       "Vui lòng thêm OPENAI_API_KEY hoặc GEMINI_API_KEY vào file .env.",
            )

        if req.stream:
            if provider == "openai":
                return StreamingResponse(
                    stream_openai_response(msgs, api_key, base_url, model, req),
                    media_type="text/event-stream",
                )
            else:  # gemini
                return StreamingResponse(
                    stream_gemini_response(msgs, api_key, model, req),
                    media_type="text/event-stream",
                )
        else:
            if provider == "openai":
                return await call_openai(msgs, api_key, base_url, model, req)
            else:
                return await call_gemini(msgs, api_key, model, req)

    # Text-only: dùng DeepSeek
    payload = {
        "model": MODEL_NAME,
        "messages": msgs,
        "stream": req.stream,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "top_p": req.top_p,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if req.stream else "application/json",
    }

    if req.stream:
        return StreamingResponse(
            stream_deepseek_response(payload, headers),
            media_type="text/event-stream",
        )
    else:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"DeepSeek API lỗi: {response.text}",
                )
            return response.json()


# ===== DeepSeek Streamer =====
async def stream_deepseek_response(payload: dict, headers: dict):
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            json=payload,
            headers=headers,
        ) as response:
            if response.status_code != 200:
                error_body = await response.aread()
                yield f"data: {json.dumps({'error': error_body.decode()})}\n\n"
                return
            async for line in response.aiter_lines():
                if line and line.startswith("data:"):
                    yield f"{line}\n\n"


# ===== OpenAI Vision =====
async def call_openai(msgs, api_key, base_url, model, req):
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": msgs,
                "temperature": req.temperature,
                "max_tokens": req.max_tokens,
            },
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"OpenAI lỗi: {resp.text}")
        return resp.json()


async def stream_openai_response(msgs, api_key, base_url, model, req):
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{base_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": msgs,
                "stream": True,
                "temperature": req.temperature,
                "max_tokens": req.max_tokens,
            },
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        ) as resp:
            if resp.status_code != 200:
                error_body = await resp.aread()
                yield f"data: {json.dumps({'error': error_body.decode()})}\n\n"
                return
            async for line in resp.aiter_lines():
                if line and line.startswith("data:"):
                    yield f"{line}\n\n"


# ===== Gemini Vision =====
def _convert_to_gemini(msgs: list) -> list:
    """Chuyển OpenAI format messages -> Gemini contents."""
    contents = []
    for msg in msgs:
        if msg["role"] == "system":
            continue  # Gemini dùng system_instruction riêng
        parts = []
        content = msg["content"]
        if isinstance(content, str):
            parts.append({"text": content})
        elif isinstance(content, list):
            for part in content:
                if part.get("type") == "text":
                    parts.append({"text": part["text"]})
                elif part.get("type") == "image_url":
                    url = part["image_url"]["url"]
                    # data:image/png;base64,xxxx
                    if url.startswith("data:"):
                        header, b64 = url.split(",", 1)
                        mime = header.split(":")[1].split(";")[0]
                        parts.append({"inline_data": {"mime_type": mime, "data": b64}})
                    else:
                        parts.append({"file_data": {"file_uri": url}})
        if parts:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": parts})
    return contents


async def call_gemini(msgs, api_key, model, req):
    system_msg = next((m["content"] for m in msgs if m["role"] == "system"), None)
    contents = _convert_to_gemini(msgs)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "contents": contents,
        "generationConfig": {"temperature": req.temperature, "maxOutputTokens": req.max_tokens},
    }
    if system_msg:
        body["systemInstruction"] = {"parts": [{"text": system_msg}]}

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=body)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"Gemini lỗi: {resp.text}")
        data = resp.json()
        text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        # Trả về format giống OpenAI cho frontend dễ parse
        return {
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "model": model,
        }


async def stream_gemini_response(msgs, api_key, model, req):
    system_msg = next((m["content"] for m in msgs if m["role"] == "system"), None)
    contents = _convert_to_gemini(msgs)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}"
    body = {
        "contents": contents,
        "generationConfig": {"temperature": req.temperature, "maxOutputTokens": req.max_tokens},
    }
    if system_msg:
        body["systemInstruction"] = {"parts": [{"text": system_msg}]}

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, json=body) as resp:
            if resp.status_code != 200:
                error_body = await resp.aread()
                yield f"data: {json.dumps({'error': error_body.decode()})}\n\n"
                return
            async for line in resp.aiter_lines():
                if line and line.startswith("data:"):
                    try:
                        data = json.loads(line[6:])
                        text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text:
                            # Convert to OpenAI SSE format
                            yield f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}\n\n"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass


@app.get("/")
async def root():
    provider, _, _, model = _get_vision_config()
    return {
        "service": "DeepSeek Chat API",
        "model": MODEL_NAME,
        "vision_provider": provider,
        "vision_model": model,
        "version": "2.1.0",
        "auth": bool(GOOGLE_CLIENT_ID),
        "messenger_bot": bool(MESSENGER_PAGE_ACCESS_TOKEN),
        "discord_bot": bool(DISCORD_BOT_TOKEN),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
