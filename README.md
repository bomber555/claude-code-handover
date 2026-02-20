# claude-code-handover

Claude Code のセッション引き継ぎ（ハンドオーバー）を自動化するフックスクリプト。

`/compact` 時やセッション復帰時に、会話履歴から引き継ぎドキュメント（`HANDOVER-{sid}-{datetime}.md`）を自動生成・読み込みする。

## 機能

| コマンド | 動作 | トリガー |
|---|---|---|
| `/compact` | ハンドオーバー自動生成 → compact 後に自動読み込み | PreCompact フック |
| `handover_update` | ハンドオーバーを手動生成（compact 不要） | UserPromptSubmit matcher |
| `handover_read` | 当セッションの最新ハンドオーバーを手動読み込み | UserPromptSubmit matcher |
| `handover_refresh` | 過去 transcript から再生成（リカバリー用） | UserPromptSubmit matcher |

## ファイル構成

```
hooks/
  pre-compact-handover.py   # ハンドオーバー生成（transcript + 過去ハンドオーバー → HANDOVER-{sid}-{datetime}.md）
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
2. 過去のハンドオーバーファイル（直近 1 件、~5KB）を読み込み
3. Claude Sonnet に引き継ぎドキュメント生成を依頼
4. `HANDOVER-{sid}-{YYYYMMDD-HHMMSS}.md` として作業ディレクトリに出力

### 読み込み（post-compact-handover.py）

**自動モード**（空 matcher、毎回 UserPromptSubmit で発火）:
- 当セッションの最新 `HANDOVER-{sid}-*.md` を読み込み
- compact 直後の初回メッセージで自動的にコンテキストに注入される

**手動モード**（`handover_read` matcher）:
- 当セッションの最新 `HANDOVER-{sid}-*.md` を読み込み
- `[handover_read]` ラベル付きで表示

### ファイル命名規則

すべてのハンドオーバーファイルは作成時からタイムスタンプ付き:

```
HANDOVER-{sid}-{YYYYMMDD-HHMMSS}.md
```

- `{sid}`: セッション ID の先頭 8 文字
- `{YYYYMMDD-HHMMSS}`: 生成日時

アーカイブ処理は不要。全ファイルが自動的に保持される。

## ハンドオーバードキュメントの構成

生成されるドキュメントは以下のセクションを含む:

- **達成事項** — セッションで完了した作業
- **未完了の作業** — 途中のタスク、発生中のエラー
- **次セッションへの指示** — 最初に実行すべきコマンド、優先順位、触ってはいけないもの
- **注意・ピットフォール** — 発見した罠、失敗パターン
- **累積コンテキスト** — 繰り返し問題、蓄積された決定事項、優先タスク Top3

### リフレッシュモード（handover_refresh）

ハンドオーバーファイルが破損・紛失した場合のリカバリー用モード。

1. 当セッションの transcript（末尾 500KB）を読み込み
2. Claude Sonnet に引き継ぎドキュメント生成を依頼

通常モード（60KB + 過去ハンドオーバー）より多くのトークンを消費するため、リカバリー目的でのみ使用すること。

## 設計判断

- **セッション ID フィルタ**: 読み込み・生成ともにセッション ID でフィルタ。異なるセッションの文脈が混入しない
- **過去コンテキストはハンドオーバーファイルから**: transcript 全文（~40KB）ではなく過去ハンドオーバー（~5KB）を読むことでトークン消費を大幅削減
- **タイムスタンプ付き命名**: 作成時から `{sid}-{datetime}` 形式。アーカイブのリネーム処理が不要で全ファイルが保持される
- **自動モードはラベルなし**: 空 matcher で毎回発火する自動モードはラベルなし（stderr のみ `[auto]`）。手動コマンド時のみ `[handover_read]` / `[handover_update]` ラベルを表示
- **生成に Claude Sonnet を使用**: transcript 解析と引き継ぎ文書生成を `claude -p --model sonnet` で実行（タイムアウト 300秒）

## 必要条件

- Claude Code CLI (`claude` コマンド)
- Python 3.8+
