#!/usr/bin/env python3
"""
PreCompact Hook: HANDOVER auto-generator
Auto-compaction前やhandover_updateコマンドでセッションの引き継ぎドキュメントを生成する。

通常モード（デフォルト）:
  過去コンテキスト: 過去ハンドオーバーファイル（1件、~5KB） + 当セッションtranscript（末尾60KB）

リフレッシュモード（--from-transcripts）:
  過去コンテキスト: 過去transcript（2件、各末尾20KB） + 当セッションtranscript（末尾100KB）
  ハンドオーバーファイル破損・紛失時のリカバリー用

ファイル命名: HANDOVER-{sid}-{YYYYMMDD-HHMMSS}.md（常にタイムスタンプ付き）

stdin: JSON payload (session_id, transcript_path, cwd, ...)
output: HANDOVER-{sid}-{datetime}.md を cwd に書き出し
"""
import sys
import json
import subprocess
import os
import glob as glob_mod
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


def find_past_transcripts(transcript_path, session_id, count=2, max_bytes=20_000):
    """過去セッションのtranscriptを取得（リフレッシュモード用）"""
    transcript_dir = os.path.dirname(transcript_path)
    current_filename = os.path.basename(transcript_path)
    sid_prefix = session_id[:8] if session_id else ""

    try:
        files = [f for f in os.listdir(transcript_dir) if f.endswith(".jsonl")]
    except Exception:
        return []

    # 自セッションのtranscriptを除外
    files = [f for f in files if f != current_filename]
    # フルパスに変換してmtimeでソート
    full_paths = [os.path.join(transcript_dir, f) for f in files]
    full_paths.sort(key=os.path.getmtime, reverse=True)

    results = []
    for path in full_paths[:count]:
        content = read_transcript_tail(path, max_bytes)
        if content.strip():
            results.append((os.path.basename(path), content))
    return results


def find_past_handovers(cwd, session_id, count=1):
    """過去のハンドオーバーファイルを取得（全セッション対象、最新N件）"""
    pattern = os.path.join(cwd, "HANDOVER-*-*.md")
    files = glob_mod.glob(pattern)
    if not files:
        return []

    sid_prefix = session_id[:8] if session_id else ""
    # 自セッションの最新は除外候補（生成直後に自分を読まないように）
    # ただし過去の自セッション分は含める
    files.sort(key=os.path.getmtime, reverse=True)
    return files[:count]


def read_file(path):
    """ファイルを読み込む"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


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

    refresh_mode = "--from-transcripts" in sys.argv

    if refresh_mode:
        # リフレッシュモード: transcript重視（当セッション100KB + 過去transcript 2件×20KB）
        current_transcript = read_transcript_tail(transcript_path, 100_000)
        if not current_transcript.strip():
            sys.exit(0)

        past_transcripts = find_past_transcripts(transcript_path, session_id, count=2, max_bytes=20_000)
        past_sections = []
        for filename, content in past_transcripts:
            past_sections.append(f"### 過去transcript: {filename}\n{content}")

        past_context = "\n\n".join(past_sections) if past_sections else "(過去transcriptなし)"
        past_count = len(past_sections)
        past_label = "past transcripts"
    else:
        # 通常モード: 当セッションtranscript(60KB) + 過去ハンドオーバー(1件)
        current_transcript = read_transcript_tail(transcript_path, 60_000)
        if not current_transcript.strip():
            sys.exit(0)

        past_handover_paths = find_past_handovers(cwd, session_id, count=1)
        past_sections = []
        for path in past_handover_paths:
            filename = os.path.basename(path)
            content = read_file(path)
            if content.strip():
                past_sections.append(f"### 過去ハンドオーバー: {filename}\n{content}")

        past_context = "\n\n".join(past_sections) if past_sections else "(過去ハンドオーバーなし)"
        past_count = len(past_sections)
        past_label = "past handovers"

    today = date.today().isoformat()
    prompt = f"""以下のClaude Codeセッションの会話履歴（JSONL）と過去のハンドオーバーを分析し、引き継ぎドキュメントを生成せよ。
当セッションの会話履歴に加え、過去{past_count}件のハンドオーバーも提供する。
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

## 累積コンテキスト
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
- 「累積コンテキスト」は過去ハンドオーバーの情報を引き継ぎつつ、現セッションの成果を統合

## 当セッション会話履歴
{current_transcript}

## 過去ハンドオーバー
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
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    handover_path = os.path.join(cwd, f"HANDOVER-{sid_short}-{ts}.md")

    try:
        with open(handover_path, "w", encoding="utf-8") as f:
            f.write(content + "\n")
    except Exception:
        sys.exit(1)

    filename = os.path.basename(handover_path)
    mode_label = "handover_refresh" if refresh_mode else "handover_update"
    print(f"[{mode_label}] {filename} generated (transcript + {past_count} {past_label})")
    print(f"[{mode_label}] {filename} generated", file=sys.stderr)


if __name__ == "__main__":
    main()
