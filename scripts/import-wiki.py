"""批量导入结构化 wiki markdown 到 SoftWiki。"""
import os, sys, glob, requests

API = os.getenv("SW_API", "http://127.0.0.1:6200")
WS = os.getenv("SW_WORKSPACE", "lsl-kb")
DIR = sys.argv[1] if len(sys.argv) > 1 else "."

# 切换工作区
r = requests.post(f"{API}/api/workspace", json={"workspace": WS})
print(f"Workspace: {r.json().get('workspace', r.json())}")

files = sorted(glob.glob(f"{DIR}/**/*.md", recursive=True))
print(f"Found {len(files)} markdown files")

for fp in files:
    rel = os.path.relpath(fp, DIR)
    # 用目录路径做标题，保留结构
    title = rel.replace(".md", "").replace(os.sep, " / ")
    with open(fp, "rb") as f:
        r = requests.post(f"{API}/api/ingest/file", files={"file": (rel, f)})
    if r.status_code == 200:
        print(f"  ✅ {rel}")
    else:
        print(f"  ❌ {rel}: {r.text[:100]}")

# 重建索引 + wiki
print("\nRebuilding index...")
r = requests.post(f"{API}/api/index")
print(f"Index: {r.json().get('status')} ({r.json().get('indexed_chunks', 0)} chunks)")
