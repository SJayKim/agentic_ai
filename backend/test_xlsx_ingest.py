#!/usr/bin/env python3
"""XLSX 인제스트 테스트 스크립트."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

async def main():
    from src.rag.lightrag_manager import ingest_single_document
    path = os.path.join(os.path.dirname(__file__), 
                        "data/documents/기술연구소_팀별기술스택및레벨별필요기술_20250521_김선준_수정.xlsx")
    path = os.path.abspath(path)
    print(f"File: {path}", flush=True)
    print(f"Exists: {os.path.exists(path)}", flush=True)
    print("Starting ingest...", flush=True)
    result = await ingest_single_document(path)
    print(f"RESULT: {result}", flush=True)

asyncio.run(main())
