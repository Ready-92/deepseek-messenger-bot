"""
Vercel Serverless entry point.
Import FastAPI app từ backend/main.py.
"""
import sys
import os

# Project root
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Cần cả 2: root để import `backend.main`, backend/ để import `messenger_bot`, `config`
sys.path.insert(0, root)
sys.path.insert(0, os.path.join(root, "backend"))

from backend.main import app
