import React, { useState, useRef, useEffect } from 'react'

const ALLOWED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']
const ALLOWED_FILE_TYPES = [
  ...ALLOWED_IMAGE_TYPES,
  'text/plain', 'text/csv', 'text/html', 'text/css', 'text/javascript',
  'application/json', 'application/pdf',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsText(file)
  })
}

function FilePreview({ file, onRemove }) {
  const [preview, setPreview] = useState('')
  useEffect(() => {
    if (file.type.startsWith('image/')) {
      readFileAsBase64(file).then(setPreview)
    }
  }, [file])

  const ext = file.name.split('.').pop()?.toUpperCase()
  const sizeStr = file.size > 1024 * 1024
    ? (file.size / 1024 / 1024).toFixed(1) + 'MB'
    : (file.size / 1024).toFixed(0) + 'KB'

  return (
    <div className="file-preview-item">
      {file.type.startsWith('image/') && preview ? (
        <img src={preview} alt={file.name} className="file-preview-img" />
      ) : (
        <span className="file-preview-icon">
          {file.type.includes('pdf') ? '📄' : file.type.includes('sheet') || file.type.includes('csv') ? '📊' : '📁'}
        </span>
      )}
      <span className="file-preview-name" title={`${file.name} (${sizeStr})`}>
        {file.name.length > 20 ? file.name.slice(0, 17) + '...' : file.name}
      </span>
      <button className="file-preview-remove" onClick={onRemove} title="Xóa file">
        ✕
      </button>
    </div>
  )
}

function ChatInput({ onSend, onStop, isLoading }) {
  const [input, setInput] = useState('')
  const [files, setFiles] = useState([])
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px'
    }
  }, [input])

  const handleSubmit = async (e) => {
    e?.preventDefault()
    if ((!input.trim() && files.length === 0) || isLoading) return

    // Xử lý file thành dữ liệu gửi đi
    const fileData = await Promise.all(
      files.map(async (file) => {
        if (file.type.startsWith('image/')) {
          const base64 = await readFileAsBase64(file)
          return { name: file.name, type: 'image', data: base64, mimeType: file.type }
        } else {
          try {
            const text = await readFileAsText(file)
            return { name: file.name, type: 'file', data: text, mimeType: file.type }
          } catch {
            return { name: file.name, type: 'file', data: `[Không thể đọc file: ${file.name}]`, mimeType: file.type }
          }
        }
      })
    )

    onSend(input.trim(), fileData)
    setInput('')
    setFiles([])
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handlePaste = (e) => {
    const items = e.clipboardData?.items
    if (!items) return

    const imageItems = []
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        imageItems.push(item)
      }
    }

    if (imageItems.length === 0) return

    e.preventDefault()
    e.stopPropagation() // Ngăn bubble lên container

    for (const item of imageItems) {
      const blob = item.getAsFile()
      if (!blob) continue

      if (blob.size > MAX_FILE_SIZE) {
        alert(`Ảnh quá lớn (${(blob.size / 1024 / 1024).toFixed(1)}MB), tối đa 10MB.`)
        continue
      }

      const ext = item.type.split('/')[1] || 'png'
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
      const fileName = `screenshot-${timestamp}.${ext}`

      const file = new File([blob], fileName, { type: item.type })
      setFiles((prev) => [...prev, file].slice(0, 10))
    }
  }

  const handleFileChange = (e) => {
    const selected = Array.from(e.target.files)
    const valid = selected.filter((f) => {
      if (f.size > MAX_FILE_SIZE) {
        alert(`File "${f.name}" vượt quá 10MB, bỏ qua.`)
        return false
      }
      if (!ALLOWED_FILE_TYPES.includes(f.type)) {
        alert(`File "${f.name}" không được hỗ trợ, bỏ qua.`)
        return false
      }
      return true
    })
    setFiles((prev) => [...prev, ...valid].slice(0, 10)) // Max 10 files
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const removeFile = (idx) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx))
  }

  return (
    <footer className="input-area">
      {/* File previews */}
      {files.length > 0 && (
        <div className="file-previews">
          {files.map((f, i) => (
            <FilePreview key={i} file={f} onRemove={() => removeFile(i)} />
          ))}
        </div>
      )}

      <div className="input-container">
        <button
          className="btn-attach"
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading}
          title="Đính kèm file/hình ảnh"
        >
          📎
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ALLOWED_FILE_TYPES.join(',')}
          onChange={handleFileChange}
          style={{ display: 'none' }}
        />
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={files.length > 0 ? 'Thêm mô tả cho file...' : 'Nhập tin nhắn... (Shift+Enter để xuống dòng)'}
          rows={1}
          disabled={isLoading}
        />
        {isLoading ? (
          <button className="btn-stop" onClick={onStop} title="Dừng">
            ⏹️
          </button>
        ) : (
          <button
            className="btn-send"
            onClick={handleSubmit}
            disabled={!input.trim() && files.length === 0}
            title="Gửi"
          >
            ➤
          </button>
        )}
      </div>
      <p className="input-hint">
        Hỗ trợ ảnh (PNG, JPEG, GIF, WebP) và file (TXT, CSV, JSON, PDF, code). Ctrl+V để dán ảnh từ clipboard. Tối đa 10MB/file.
      </p>
    </footer>
  )
}

export default ChatInput
