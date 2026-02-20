# claude-code-handover

Claude Code のセッション引き継ぎ（ハンドオーバー）を自動化するフックスクリプト。

`/compact` 時やセッション復帰時に、会話履歴から引き継ぎドキュメント（`HANDOVER-{session_id}.md`）を自動生成・読み込みする。

## 機能

| コマンド | 動作 | トリガー |
|---|---|---|
| `/compact` | ハンドオーバー自動生成 → compact 後に自動読み込み | PreCompact フック |
| `handover_update` | ハンドオーバーを手動生成（compact 不要） | UserPromptSubmit matcher |
| `handover_read` | 最新のハンドオーバーを手動読み込み | UserPromptSubmit matcher |

## ファイル構成

```
hooks/
  pre-compact-handover.py   # ハンドオーバー生成（transcript → HANDOVER-{sid}.md）
  post-compact-handover.py  # ハンドオーバー読み込み（自動 / 手動）
settings.example.json       # ~/.claude/settings.json に追加するフック設定
```

## セットアップ

### 1. フックスクリプトを配置

```bash
cp hooks/pre-compact-handover.py ~/.claude/hooks/
cp hooks/post-compact-handover.py ~/.claude/hooks/
chmod +x ~/.claude/hooks/pre-compact-handover.py
chmod +x ~/.claude/hooks/post-compact-handover.py
```

### 2. settings.json にフック設定を追加

`settings.example.json` の内容を `~/.claude/settings.json` の `hooks` セクションにマージする。

既存の `hooks` がある場合は、各イベント（`UserPromptSubmit`, `PreCompact`）の配列に追加する。

## 動作の仕組み

### 生成（pre-compact-handover.py）

1. 現在のセッションの transcript（末尾 60KB）を読み込み
2. 同一セッション ID の過去 transcript があれば追加読み込み（末尾 20KB × 最大2件）
3. Claude Sonnet に引き継ぎドキュメント生成を依頼
4. `HANDOVER-{session_id[:8]}.md` として作業ディレクトリに出力
5. 既存ファイルはタイムスタンプ付きにアーカイブ

### 読み込み（post-compact-handover.py）

**自動モード**（空 matcher、毎回 UserPromptSubmit で発火）:
- `HANDOVER-{session_id}.md` が存在すれば読み込み → タイムスタンプ付きにアーカイブ
- compact 直後の初回メッセージで自動的にコンテキストに注入される

**手動モード**（`handover_read` matcher）:
- 作業ディレクトリ内の最新 `HANDOVER-*.md` を読み込み（アーカイブしない）
- 別セッションのハンドオーバーも読める

### ファイル命名規則

| 状態 | ファイル名 |
|---|---|
| 最新（未読み込み） | `HANDOVER-{sid}.md` |
| アーカイブ済み | `HANDOVER-{sid}-{YYYYMMDD-HHMMSS}.md` |

## ハンドオーバードキュメントの構成

生成されるドキュメントは以下のセクションを含む:

- **達成事項** — セッションで完了した作業
- **未完了の作業** — 途中のタスク、発生中のエラー
- **次セッションへの指示** — 最初に実行すべきコマンド、優先順位、触ってはいけないもの
- **注意・ピットフォール** — 発見した罠、失敗パターン
- **累積コンテキスト** — 繰り返し問題、蓄積された決定事項、優先タスク Top3

## 設計判断

- **セッション ID フィルタ**: 過去 transcript の読み込みは同一セッション ID に限定。異なるセッションの文脈が混入しない
- **自動モードはラベルなし**: 空 matcher で毎回発火する自動モードは `[auto]` ラベルのみ（stderr）。手動コマンド時のみ `[handover_read]` / `[handover_update]` ラベルを表示
- **生成に Claude Sonnet を使用**: transcript 解析と引き継ぎ文書生成を `claude -p --model sonnet` で実行（タイムアウト 300秒）

## 必要条件

- Claude Code CLI (`claude` コマンド)
- Python 3.8+
