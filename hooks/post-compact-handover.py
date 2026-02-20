#!/usr/bin/env python3
"""
Post-Compact HANDOVER Loader
HANDOVERファイルの存在自体をフラグとして利用。別途フラグファイル不要。

自動モード: HANDOVER-{sid}.md が存在すれば読み込み → タイムスタンプ付きにリネーム（アーカイブ）
手動モード (--load): cwd 内の最新 HANDOVER-*.md を読み込み（保持）

ファイル命名規則:
  最新（未読み込み）: HANDOVER-{sid}.md
  アーカイブ済み:     HANDOVER-{sid}-{YYYYMMDD-HHMMSS}.md

stdin: JSON payload (session_id, cwd, ...)
stdout: HANDOVERドキュメント内容（Claudeのコンテキストに注入）
stderr: ステータスメッセージ（1行でファイル名を通知）
"""
import sys
import json
import os
import glob as glob_mod
from datetime import datetime


def find_latest_handover(cwd):
    """最新のHANDOVER-*.mdを探す（アーカイブ含む）"""
    pattern = os.path.join(cwd, "HANDOVER-*.md")
    files = glob_mod.glob(pattern)
    if not files:
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


def archive(path, sid):
    """HANDOVER-{sid}.md → HANDOVER-{sid}-{timestamp}.md にリネーム"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    cwd = os.path.dirname(path)
    archived = os.path.join(cwd, f"HANDOVER-{sid}-{timestamp}.md")
    try:
        os.rename(path, archived)
    except Exception:
        pass


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        payload = {}

    cwd = payload.get("cwd", "")
    if not cwd or not os.path.isdir(cwd):
        sys.exit(0)

    if "--load" in sys.argv:
        # 手動モード: 最新のHANDOVERを読み込み（ファイル保持）
        path = find_latest_handover(cwd)
        if path:
            load_and_output(path, label="handover_read")
    else:
        # 自動モード: 現在セッションのHANDOVERを読み込み → アーカイブ（ラベルなし）
        session_id = payload.get("session_id", "")
        if not session_id:
            sys.exit(0)
        sid = session_id[:8]
        path = os.path.join(cwd, f"HANDOVER-{sid}.md")
        if os.path.isfile(path):
            if load_and_output(path):
                archive(path, sid)


if __name__ == "__main__":
    main()
