# 🤖 DeepSeek Chat - AI Assistant

Web chat AI + Messenger Bot sử dụng **DeepSeek V4 Pro** API.

## 🏗️ Kiến trúc

```
deepseek-chat-app/
├── backend/           # FastAPI Python backend
│   ├── main.py        # API server + DeepSeek proxy
│   ├── config.py      # Cấu hình
│   ├── messenger_bot.py # Facebook Messenger Bot
│   ├── requirements.txt
│   └── .env           # API key (tự tạo từ .env.example)
├── frontend/          # React + Vite frontend
│   ├── src/
│   │   ├── App.jsx            # Component chính
│   │   ├── App.css            # Styles
│   │   └── components/
│   │       ├── ChatMessage.jsx  # Hiển thị tin nhắn + Markdown
│   │       └── ChatInput.jsx    # Ô nhập liệu
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
└── README.md
```

## 🚀 Cài đặt & Chạy

### 1. Cấu hình API Key

```bash
cd backend
cp .env.example .env
# Sửa file .env, thêm DeepSeek API Key của bạn:
# DEEPSEEK_API_KEY=sk-your-actual-api-key
```

### 2. Cài đặt Backend

```bash
cd backend
pip install -r requirements.txt
python main.py
# Server chạy tại http://localhost:8000
```

### 3. Cài đặt Frontend

```bash
cd frontend
npm install
npm run dev
# Frontend chạy tại http://localhost:3000
```

### 4. Mở trình duyệt

Truy cập **http://localhost:3000** để bắt đầu chat!

## ✨ Tính năng

- 🎨 **Giao diện Dark Mode** hiện đại, đẹp mắt
- 💬 **Streaming response** - phản hồi real-time từng chữ
- 📝 **Hỗ trợ Markdown** - hiển thị code blocks, bảng, danh sách
- 🎯 **Syntax Highlighting** - tô màu code với nhiều ngôn ngữ
- 📋 **Copy code** - sao chép code chỉ với 1 click
- ⏹️ **Dừng phản hồi** - nút stop khi đang streaming
- 🌐 **Hỗ trợ tiếng Việt** - hệ thống prompt mặc định trả lời tiếng Việt
- 📱 **Responsive** - hiển thị tốt trên mọi thiết bị

## 🔧 Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite |
| Styling | CSS Custom Properties (Dark Theme) |
| Markdown | react-markdown + react-syntax-highlighter |
| Backend | Python FastAPI |
| Streaming | Server-Sent Events (SSE) |
| AI Model | DeepSeek V4 Pro (deepseek-chat) |

## 📦 API Endpoints

| Method | Endpoint | Mô tả |
|--------|---------|-------|
| GET | `/` | Health check |
| POST | `/api/chat` | Gửi tin nhắn (hỗ trợ streaming) |

### Request Body (`POST /api/chat`)

```json
{
  "messages": [
    {"role": "system", "content": "Bạn là trợ lý AI..."},
    {"role": "user", "content": "Xin chào"}
  ],
  "stream": true,
  "temperature": 0.7,
  "max_tokens": 4096
}
```

---

## 🤖 Messenger Bot (Facebook)

Bot AI trả lời tự động trên Facebook Messenger.

### Cấu hình

```bash
# Thêm vào backend/.env:
MESSENGER_VERIFY_TOKEN=deepseek_bot_verify_2026
MESSENGER_PAGE_ACCESS_TOKEN=EAAxxx...  # Từ Facebook Developer
```

| Endpoint | Mô tả |
|----------|-------|
| `GET /messenger/webhook` | Xác thực webhook Facebook |
| `POST /messenger/webhook` | Nhận tin nhắn từ Messenger |

### Lệnh chat

| Lệnh | Chức năng |
|------|-----------|
| `/help` | Hiển thị trợ giúp |
| `/reset` | Xóa lịch sử chat |

---

## ☁️ Deploy 24/7 lên Render (Free)

### 1. Push code lên GitHub

```bash
git init
git add .
git commit -m "feat: DeepSeek Messenger Bot"
# Tạo repo trên GitHub → push
```

### 2. Deploy Render

```
👉 Vào https://render.com → New Web Service
👉 Connect GitHub repo
👉 Render tự đọc file render.yaml
👉 Add Env Vars: DEEPSEEK_API_KEY, MESSENGER_PAGE_ACCESS_TOKEN
👉 Deploy → URL: https://deepseek-messenger-bot.onrender.com
```

### 3. Cập nhật Webhook Facebook

```
👉 Webhook URL: https://deepseek-messenger-bot.onrender.com/messenger/webhook
👉 Verify Token: deepseek_bot_verify_2026
```

Bot chạy 24/7, không cần bật máy tính! 🎉
