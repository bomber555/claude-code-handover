#!/usr/bin/env python3
"""
PreCompact Hook: HANDOVER.md auto-generator
Auto-compaction前にセッションの引き継ぎドキュメントを自動生成する。
過去3セッション分のtranscriptを累積分析し、文脈の連続性を保った引き継ぎを作成。

stdin: JSON payload (session_id, transcript_path, cwd, trigger, ...)
output: HANDOVER.md を cwd に書き出し
"""
import sys
import json
import subprocess
import os
from datetime import date, datetime


def read_transcript_tail(path, max_bytes):
    """transcriptの末尾をmax_bytesだけ読み込む"""
    try:
        size = os.path.getsize(path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            if size > max_bytes:
                f.seek(max(0, size - max_bytes))
                f.readline()  # 途切れた行をスキップ
            return f.read()
    except Exception:
        return ""


def find_past_transcripts(transcript_path, session_id, count=2):
    """現在のセッション以外の同一セッションのtranscriptファイルを取得"""
    project_dir = os.path.dirname(transcript_path)
    if not os.path.isdir(project_dir):
        return []

    current_basename = os.path.basename(transcript_path)
    sid_prefix = session_id[:8] if session_id else ""
    jsonl_files = []
    for f in os.listdir(project_dir):
        if not f.endswith(".jsonl"):
            continue
        if f == current_basename:
            continue
        # 自分のセッションIDに一致するもののみ（他セッションの文脈混入を防止）
        if sid_prefix and not f.startswith(sid_prefix):
            continue
        full_path = os.path.join(project_dir, f)
        # 5KB未満のファイルはスキップ（些末なセッション）
        if os.path.getsize(full_path) < 5000:
            continue
        jsonl_files.append((full_path, os.path.getmtime(full_path)))

    # 更新日時の新しい順にソート
    jsonl_files.sort(key=lambda x: x[1], reverse=True)
    return [path for path, _ in jsonl_files[:count]]


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(1)

    transcript_path = payload.get("transcript_path", "")
    session_id = payload.get("session_id", "unknown")
    cwd = payload.get("cwd", "")

    if not transcript_path or not os.path.isfile(transcript_path):
        sys.exit(0)
    if not cwd or not os.path.isdir(cwd):
        sys.exit(0)

    # 現在のセッション: 末尾60KB
    current_transcript = read_transcript_tail(transcript_path, 60_000)
    if not current_transcript.strip():
        sys.exit(0)

    # 過去2セッション: 各末尾20KB
    past_paths = find_past_transcripts(transcript_path, session_id, count=2)
    past_sections = []
    for i, past_path in enumerate(past_paths):
        sid = os.path.basename(past_path).replace(".jsonl", "")[:8]
        content = read_transcript_tail(past_path, 20_000)
        if content.strip():
            past_sections.append(f"### 過去セッション {i+1} (session: {sid})\n{content}")

    past_context = "\n\n".join(past_sections) if past_sections else "(過去セッションデータなし)"
    past_count = len(past_sections)

    today = date.today().isoformat()
    prompt = f"""以下のClaude Codeセッションの会話履歴（JSONL）を分析し、引き継ぎドキュメントを生成せよ。
現在のセッションに加え、過去{past_count}セッション分のデータも提供する。
累積的な分析を行い、セッション間の文脈の連続性と繰り返しパターンを把握すること。

## 出力フォーマット（このまま出力）

# HANDOVER — {today}
Session: {session_id[:8]}
Directory: {cwd}

## 達成事項
（箇条書き。具体的ファイル名・変更内容を含む）

## 未完了の作業
（途中のタスク、発生中のエラー。ファイルパス・行番号を含む）

## 次セッションへの指示
1. 最初に実行すべきコマンド／確認事項
2. 残タスクの優先順位
3. 触ってはいけないファイル／機能

## 注意・ピットフォール
（セッション中に発見した罠、失敗パターン）

## 累積コンテキスト（過去3セッション分析）
- 繰り返し発生している問題:
- セッション間で蓄積された決定事項:
- 次に優先すべきタスクTop3:

---
ルール:
- prescriptive（指示型）で書く。「確認した」ではなく「実行せよ」
- 具体的パス・コマンド・変数名を含める
- 前置き不要。即座にMarkdownを出力
- 日本語で記述
- 「達成事項」「未完了の作業」「次セッションへの指示」「注意・ピットフォール」は現在のセッションを中心に記述
- 「累積コンテキスト」は過去セッションも含めた横断分析。繰り返しミス・蓄積された決定・優先タスクを抽出

## 現在のセッション会話履歴
{current_transcript}

## 過去セッションのデータ
{past_context}"""

    # CLAUDECODE環境変数を除去（ネストセッション制限の回避）
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "sonnet"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=cwd,
            env=env,
        )
        content = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        sys.exit(1)

    if not content:
        sys.exit(1)

    sid_short = session_id[:8]
    handover_path = os.path.join(cwd, f"HANDOVER-{sid_short}.md")

    # 既存ファイルがあればタイムスタンプ付きにアーカイブ
    if os.path.isfile(handover_path):
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        archived = os.path.join(cwd, f"HANDOVER-{sid_short}-{ts}.md")
        try:
            os.rename(handover_path, archived)
        except Exception:
            pass

    try:
        with open(handover_path, "w", encoding="utf-8") as f:
            f.write(content + "\n")
    except Exception:
        sys.exit(1)

    print(f"[handover_update] HANDOVER-{sid_short}.md generated ({1 + past_count} sessions analyzed)")
    print(f"[handover_update] HANDOVER-{sid_short}.md generated", file=sys.stderr)


if __name__ == "__main__":
    main()
