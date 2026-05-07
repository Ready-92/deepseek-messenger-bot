import React, { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'

function ChatMessage({ message, isStreaming = false }) {
  const isUser = message.role === 'user'
  const isError = message.isError
  const [expandedFiles, setExpandedFiles] = useState({})

  const files = message.files || []

  return (
    <div className={`message-row ${isUser ? 'user' : 'assistant'} ${isError ? 'error' : ''}`}>
      <div className="message-avatar">
        {isUser ? '👤' : isError ? '⚠️' : '🤖'}
      </div>
      <div className="message-bubble">
        {/* File/image attachments */}
        {files.length > 0 && (
          <div className="message-attachments">
            {files.map((file, idx) => {
              const isExpanded = expandedFiles[idx]
              if (file.type === 'image') {
                // Nếu data đã bị strip khỏi localStorage, hiển thị placeholder
                if (!file.data || file.data === '[IMAGE]') {
                  return (
                    <div key={idx} className="attachment-image-wrapper">
                      <div className="attachment-image-placeholder">🖼️ {file.name}</div>
                    </div>
                  )
                }
                return (
                  <div key={idx} className="attachment-image-wrapper">
                    <img
                      src={file.data}
                      alt={file.name}
                      className="attachment-image"
                      onClick={() => window.open(file.data, '_blank')}
                      onError={(e) => {
                        e.target.style.display = 'none'
                        e.target.parentElement.innerHTML = '<div class="attachment-image-placeholder">🖼️ Ảnh không khả dụng</div>'
                      }}
                    />
                  </div>
                )
              }
              return (
                <div key={idx} className="attachment-file">
                  <div
                    className="attachment-file-header"
                    onClick={() => setExpandedFiles((prev) => ({ ...prev, [idx]: !isExpanded }))}
                  >
                    <span className="attachment-file-icon">
                      {file.name.endsWith('.pdf') ? '📄' : file.name.endsWith('.csv') ? '📊' : '📁'}
                    </span>
                    <span className="attachment-file-name">{file.name}</span>
                    <span className="attachment-file-toggle">{isExpanded ? '▲' : '▼'}</span>
                  </div>
                  {isExpanded && (
                    <pre className="attachment-file-content">{file.data}</pre>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Text content */}
        {message.content && (
          isUser ? (
            <p>{message.content}</p>
          ) : (
            <div className="markdown-body">
              <ReactMarkdown
                components={{
                  code({ node, inline, className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '')
                    return !inline && match ? (
                      <div className="code-block">
                        <div className="code-header">
                          <span>{match[1]}</span>
                          <button
                            className="copy-btn"
                            onClick={() => navigator.clipboard.writeText(String(children).replace(/\n$/, ''))}
                          >
                            📋 Copy
                          </button>
                        </div>
                        <SyntaxHighlighter
                          style={oneDark}
                          language={match[1]}
                          PreTag="div"
                          {...props}
                        >
                          {String(children).replace(/\n$/, '')}
                        </SyntaxHighlighter>
                      </div>
                    ) : (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    )
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
              {isStreaming && <span className="cursor-blink">▊</span>}
            </div>
          )
        )}
      </div>
    </div>
  )
}

export default ChatMessage
