#!/usr/bin/env bash
# PreToolUse hook for Edit|Write|NotebookEdit
# Blocks modification of protected files in this project.
#
# Protected:
#   - backend/.env                         (API keys)
#   - data/rag_storage/**                  (LightRAG state: graphml, vdb_*, kv_store_*)
#   - data/documents/**                    (uploaded originals)
#   - data/document_summaries.json         (summary cache — expensive to rebuild)
#   - any *.env / *.pem / *.key            (generic secrets)
#
# Reads tool input JSON from stdin, extracts file_path, exits 2 to block.

FILE=$(python -c "
import sys, json
try:
    data = json.load(sys.stdin)
    path = data.get('tool_input', {}).get('file_path', '') or \
           data.get('tool_input', {}).get('notebook_path', '')
    print(path)
except Exception:
    pass
" 2>/dev/null)

[ -z "$FILE" ] && exit 0

# Normalize to forward slashes for matching
NORM=$(echo "$FILE" | tr '\\' '/')

case "$NORM" in
    *"/backend/.env"|*"/backend/.env."*|*".env"|*".env."*)
        echo "Blocked: .env contains API keys. Edit manually outside Claude." >&2
        exit 2 ;;
    *"/data/rag_storage/"*)
        echo "Blocked: data/rag_storage/** is LightRAG internal state. Rebuild via /api/ingest or delete the directory manually." >&2
        exit 2 ;;
    *"/data/documents/"*)
        echo "Blocked: data/documents/** are uploaded originals. Add/remove via the frontend upload UI or manually outside Claude." >&2
        exit 2 ;;
    *"/data/document_summaries.json")
        echo "Blocked: document_summaries.json is an LLM-generated cache. Delete to force rebuild, don't edit in place." >&2
        exit 2 ;;
    *.pem|*.key)
        echo "Blocked: secret file ($FILE)." >&2
        exit 2 ;;
esac

exit 0
