import React, { useState, useRef, useEffect, useCallback } from 'react'
import ChatMessage from './components/ChatMessage'
import ChatInput from './components/ChatInput'
import './App.css'

const SYSTEM_PROMPT = {
  role: 'system',
  content: 'Bạn là DeepSeek V4 Pro, một trợ lý AI thông minh và hữu ích. Hãy trả lời bằng tiếng Việt khi người dùng nói tiếng Việt. Trả lời chi tiết, chính xác và thân thiện.',
}

const STORAGE_KEY = 'deepseek-chat-sessions'

function createNewSession() {
  return {
    id: Date.now().toString() + Math.random().toString(36).slice(2, 6),
    title: 'Cuộc trò chuyện mới',
    messages: [],
  }
}

function loadSessions() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const sessions = JSON.parse(saved)
      if (Array.isArray(sessions) && sessions.length > 0) return sessions
    }
  } catch { /* ignore */ }
  return [createNewSession()]
}

function getSessionTitle(messages) {
  const firstUser = messages.find((m) => m.role === 'user')
  if (!firstUser) return 'Cuộc trò chuyện mới'
  const text = typeof firstUser.content === 'string'
    ? firstUser.content
    : firstUser.content.find((c) => c.type === 'text')?.text || ''
  return text.slice(0, 50) + (text.length > 50 ? '...' : '')
}

function App() {
  const [chatSessions, setChatSessions] = useState(loadSessions)
  const [activeChatId, setActiveChatId] = useState(() => chatSessions[0]?.id || '')
  const [isLoading, setIsLoading] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const messagesEndRef = useRef(null)
  const abortControllerRef = useRef(null)

  // Lấy session hiện tại
  const activeSession = chatSessions.find((s) => s.id === activeChatId) || chatSessions[0]
  const messages = activeSession?.messages || []

  // Lưu sessions vào localStorage (strip ảnh base64 để tránh tràn quota)
  useEffect(() => {
    try {
      const lite = chatSessions.map((s) => ({
        ...s,
        messages: s.messages.map((m) => ({
          ...m,
          files: (m.files || []).map((f) =>
            f.type === 'image'
              ? { ...f, data: '[IMAGE]' } // strip base64, giữ metadata
              : f
          ),
          // Strip base64 khỏi multimodal content
          content: Array.isArray(m.content)
            ? m.content.map((part) => {
                if (part.type === 'image_url') return { type: 'image_url', image_url: { url: '[IMAGE]' } }
                return part
              })
            : m.content,
        })),
      }))
      localStorage.setItem(STORAGE_KEY, JSON.stringify(lite))
    } catch (e) {
      console.warn('localStorage.full:', e.message)
      // Xóa session cũ nhất nếu đầy
      try {
        const existingStr = localStorage.getItem(STORAGE_KEY)
        if (existingStr) {
          const existing = JSON.parse(existingStr)
          existing.shift()
          localStorage.setItem(STORAGE_KEY, JSON.stringify(existing))
        }
      } catch { /* bỏ qua */ }
    }
  }, [chatSessions])

  // Cập nhật messages trong active session
  const updateMessages = useCallback((newMessages) => {
    setChatSessions((prev) =>
      prev.map((s) =>
        s.id === activeChatId
          ? { ...s, messages: newMessages, title: getSessionTitle(newMessages) }
          : s
      )
    )
  }, [activeChatId])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, streamingContent])

  const handleSend = useCallback(async (userMessage, fileData = []) => {
    if ((!userMessage.trim() && fileData.length === 0) || isLoading) return

    // Xây dựng nội dung tin nhắn (hỗ trợ multimodal cho ảnh)
    let messageContent = userMessage
    const messageFiles = fileData.map((f) => ({ name: f.name, type: f.type, data: f.data, mimeType: f.mimeType }))

    const hasImages = fileData.some((f) => f.type === 'image')
    if (hasImages) {
      const textParts = []
      const imageParts = []
      fileData.forEach((f) => {
        if (f.type === 'image') {
          imageParts.push({ type: 'image_url', image_url: { url: f.data } })
        } else {
          textParts.push(`\n[File: ${f.name}]\n\`\`\`\n${f.data.slice(0, 4000)}\n\`\`\``)
        }
      })
      const fullText = userMessage + textParts.join('\n')
      messageContent = [
        { type: 'text', text: fullText || 'Mô tả hình ảnh này' },
        ...imageParts,
      ]
    } else if (fileData.length > 0) {
      // Chỉ có file text: ghép nội dung vào message
      const fileTexts = fileData.map((f) =>
        `\n[File: ${f.name}]\n\`\`\`\n${f.data.slice(0, 4000)}\n\`\`\``
      ).join('\n')
      messageContent = (userMessage || 'Phân tích file này:') + fileTexts
    }

    const newUserMsg = { role: 'user', content: messageContent, files: messageFiles }
    const updatedMessages = [...messages, newUserMsg]
    updateMessages(updatedMessages)
    setIsLoading(true)
    setStreamingContent('')

    const controller = new AbortController()
    abortControllerRef.current = controller

    try {
      // Strip `files` property khỏi messages trước khi gửi (tránh gửi base64 thừa)
      const cleanMessages = [SYSTEM_PROMPT, ...updatedMessages].map(({ role, content }) => ({ role, content }))

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: cleanMessages,
          stream: true,
          temperature: 0.7,
          max_tokens: 4096,
        }),
        signal: controller.signal,
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Lỗi kết nối đến server')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let assistantContent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim()
            if (data === '[DONE]') continue

            try {
              const parsed = JSON.parse(data)
              // Kiểm tra lỗi từ API (cả DeepSeek lẫn backend tự gửi)
              if (parsed.error) {
                const errMsg = typeof parsed.error === 'string' ? parsed.error : JSON.stringify(parsed.error)
                throw new Error(errMsg)
              }
              const delta = parsed.choices?.[0]?.delta?.content
              if (delta) {
                assistantContent += delta
                setStreamingContent(assistantContent)
              }
            } catch (e) {
              // Nếu là lỗi API (có message) thì throw luôn
              if (e.message && !e.message.includes('position')) {
                reader.cancel()
                throw e
              }
              // bỏ qua dòng không parse được
            }
          }
        }
      }

      if (assistantContent) {
        const finalMessages = [...updatedMessages, { role: 'assistant', content: assistantContent }]
        updateMessages(finalMessages)
      }
    } catch (err) {
      if (err.name === 'AbortError') return
      const errorMessages = [
        ...updatedMessages,
        { role: 'assistant', content: `❌ Lỗi: ${err.message}`, isError: true },
      ]
      updateMessages(errorMessages)
    } finally {
      setIsLoading(false)
      setStreamingContent('')
      abortControllerRef.current = null
    }
  }, [messages, isLoading, updateMessages])

  const handleStop = () => {
    abortControllerRef.current?.abort()
  }

  const handleClear = () => {
    if (isLoading) return
    updateMessages([])
    setStreamingContent('')
  }

  // ---- Sidebar handlers ----
  const handleNewChat = () => {
    const newSession = createNewSession()
    setChatSessions((prev) => [newSession, ...prev])
    setActiveChatId(newSession.id)
    setSidebarOpen(false)
  }

  const handleSelectChat = (id) => {
    if (isLoading) {
      abortControllerRef.current?.abort()
      setIsLoading(false)
      setStreamingContent('')
    }
    setActiveChatId(id)
    setSidebarOpen(false)
  }

  const handleDeleteChat = (id, e) => {
    e.stopPropagation()
    setChatSessions((prev) => {
      const filtered = prev.filter((s) => s.id !== id)
      return filtered.length === 0 ? [createNewSession()] : filtered
    })
    if (id === activeChatId) {
      const remaining = chatSessions.filter((s) => s.id !== id)
      setActiveChatId(remaining[0]?.id || '')
    }
  }

  return (
    <div className="app-container">
      {/* ===== Sidebar ===== */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <button className="btn-new-chat" onClick={handleNewChat}>
            <span>➕</span> Đoạn chat mới
          </button>
        </div>
        <div className="sidebar-list">
          {chatSessions.map((session) => (
            <div
              key={session.id}
              className={`chat-history-item ${session.id === activeChatId ? 'active' : ''}`}
              onClick={() => handleSelectChat(session.id)}
            >
              <span className="chat-history-icon">💬</span>
              <span className="chat-history-title">{session.title}</span>
              <button
                className="chat-history-delete"
                onClick={(e) => handleDeleteChat(session.id, e)}
                title="Xóa"
              >
                🗑️
              </button>
            </div>
          ))}
        </div>
      </aside>

      {/* ===== Overlay for mobile ===== */}
      {sidebarOpen && (
        <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />
      )}

      {/* ===== Main Chat Area ===== */}
      <div className="app">
        {/* Header */}
        <header className="header">
          <div className="header-content">
            <div className="header-brand">
              <button
                className="btn-sidebar-toggle"
                onClick={() => setSidebarOpen(!sidebarOpen)}
                title="Lịch sử chat"
              >
                ☰
              </button>
              <span className="logo">🤖</span>
              <div>
                <h1>DeepSeek Chat</h1>
                <span className="model-badge">V4 Pro</span>
              </div>
            </div>
            <button className="btn-clear" onClick={handleClear} disabled={isLoading}>
              🗑️ Xóa chat
            </button>
          </div>
        </header>

        {/* Chat Area */}
        <main className="chat-area">
          {messages.length === 0 && !isLoading && (
            <div className="welcome">
              <div className="welcome-icon">🤖</div>
              <h2>Chào mừng đến với DeepSeek Chat</h2>
              <p>Trợ lý AI thông minh, sử dụng model <strong>DeepSeek V4 Pro</strong></p>
              <div className="suggestions">
                <button onClick={() => handleSend('Giải thích về machine learning cho người mới bắt đầu')}>
                  💡 Machine Learning là gì?
                </button>
                <button onClick={() => handleSend('Viết một bài thơ về mùa xuân bằng tiếng Việt')}>
                  🌸 Thơ về mùa xuân
                </button>
                <button onClick={() => handleSend('Hướng dẫn tôi cách tạo một REST API với FastAPI')}>
                  🚀 Tạo REST API với FastAPI
                </button>
                <button onClick={() => handleSend('Giải thích sự khác nhau giữa AI, Machine Learning và Deep Learning')}>
                  🧠 AI vs ML vs DL
                </button>
              </div>
            </div>
          )}

          {messages.map((msg, idx) => (
            <ChatMessage key={idx} message={msg} />
          ))}

          {isLoading && streamingContent && (
            <ChatMessage
              message={{ role: 'assistant', content: streamingContent }}
              isStreaming
            />
          )}

          {isLoading && !streamingContent && (
            <div className="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </main>

        {/* Input Area */}
        <ChatInput
          onSend={handleSend}
          onStop={handleStop}
          isLoading={isLoading}
        />
      </div>
    </div>
  )
}

export default App
