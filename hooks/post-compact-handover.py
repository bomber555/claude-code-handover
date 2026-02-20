#!/usr/bin/env python3
"""
Post-Compact HANDOVER Loader

自動モード: 当セッションの最新 HANDOVER-{sid}-*.md を読み込み
手動モード (--load): cwd 内の最新 HANDOVER-*.md を読み込み

ファイル命名規則:
  HANDOVER-{sid}-{YYYYMMDD-HHMMSS}.md（全ファイルタイムスタンプ付き、アーカイブ不要）

stdin: JSON payload (session_id, cwd, ...)
stdout: HANDOVERドキュメント内容（Claudeのコンテキストに注入）
stderr: ステータスメッセージ
"""
import sys
import json
import os
import glob as glob_mod


def find_latest_handover(cwd, sid_prefix=None):
    """最新のHANDOVER-*.mdを探す"""
    if sid_prefix:
        pattern = os.path.join(cwd, f"HANDOVER-{sid_prefix}-*.md")
    else:
        pattern = os.path.join(cwd, "HANDOVER-*-*.md")
    files = glob_mod.glob(pattern)
    if not files:
        # フォールバック: タイムスタンプなしの旧形式
        if sid_prefix:
            legacy = os.path.join(cwd, f"HANDOVER-{sid_prefix}.md")
            if os.path.isfile(legacy):
                return legacy
        legacy = os.path.join(cwd, "HANDOVER.md")
        return legacy if os.path.isfile(legacy) else None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


def load_and_output(path, label=None):
    """HANDOVERファイルを読み込んでstdoutに出力"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return False
    if not content.strip():
        return False
    filename = os.path.basename(path)
    if label:
        print(f"[{label}] {filename} loaded")
    print(content)
    print(f"[{label or 'auto'}] {filename} loaded", file=sys.stderr)
    return True


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        payload = {}

    cwd = payload.get("cwd", "")
    if not cwd or not os.path.isdir(cwd):
        sys.exit(0)

    session_id = payload.get("session_id", "")
    sid = session_id[:8] if session_id else None

    if "--load" in sys.argv:
        # 手動モード: 当セッションの最新HANDOVERを読み込み
        path = find_latest_handover(cwd, sid_prefix=sid)
        if path:
            load_and_output(path, label="handover_read")
    else:
        # 自動モード: 当セッションの最新HANDOVERを読み込み
        if not sid:
            sys.exit(0)
        path = find_latest_handover(cwd, sid_prefix=sid)
        if path:
            load_and_output(path)


if __name__ == "__main__":
    main()
