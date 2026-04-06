# virtual-reviewer

LLM専門家モデルを活用し、セキュリティレビュー依頼の一次評価を自動化するAIセキュリティレビューシステム。

> **ステータス: PoC（概念実証）。** アーキテクチャ定義済み、コアパイプライン実装・検証済み。

## コンセプト

従来のRAGベースのアプローチは検索精度がシステムの性能上限となる。virtual-reviewer は検索そのものを排除する — 各専門家モデルが担当規定の全文をコンテキストに保持し、否定条件・例外・相互参照を含む厳密な規定適用を可能にする。

## 設計思想

UNIX哲学に従う。各モジュールは1つのことをうまくやり、stdin/stdoutのJSONで通信し、stderrにログを出力する。

```bash
# フルパイプライン
cat application.json \
  | vr-intake --profiles-dir profiles/ \
  | vr-orchestrate --profiles-dir profiles/ \
  | vr-brain \
  | tee assessment.json \
  | vr-report > report.md
```

## アーキテクチャ

```
規定文書 (.md) → vr-compile → 専門家定義群 (オフライン)

申請資料 → vr-intake → vr-orchestrate → vr-brain → vr-report
(マルチモーダル) (構造化)    (専門家モデル群)  (最終判定)  (Markdown)
```

### モジュール一覧

| コマンド | 役割 | モデル | LLM |
|---|---|---|---|
| `vr-compile` | 規定Markdownを専門家定義にコンパイル | gemini-2.5-pro | Yes |
| `vr-intake` | 申請資料を構造化データに変換（マルチモーダル、2パスQ&A） | gemini-2.5-pro | Yes |
| `vr-orchestrate` | 専門家モデルに並列配信し、判定を収集 | gemini-2.5-flash / pro | Yes |
| `vr-brain` | 矛盾解消、複合リスク評価、最終判定の生成 | gemini-2.5-pro | Yes |
| `vr-report` | FinalAssessmentを日本語Markdownレポートに変換 | — | No |
| `vr-questions` | インテークの追加質問からQ&Aシートを生成 | — | No |
| `vr-answers` | 記入済みQ&Aシートを解析し、2パス目のIntakeInputを生成 | — | No |

全LLMモジュールはGoogle Cloud Vertex AI APIを`google-genai` SDK経由で使用。ADC認証。モデルは環境変数で切り替え可能。

## 主要な設計判断

- **RAG不使用**: 専門家モデルが規定全文をコンテキストに保持 — 検索不要
- **UNIX哲学**: stdin/stdout JSON、stderr JSONLログ、パイプで結合可能
- **モジュール間は構造化データで通信**: Pydanticバリデーション済みJSONスキーマ、自然言語ではない
- **対話的インテーク**: マルチモーダルLLMが申請資料を解析し、不足情報のQ&Aシートを生成
- **監査証跡**: 全モジュール境界でSHA-256ハッシュチェーンを記録し改竄検知
- **分散実行対応**: モジュールは場所透過 — SSHパイプでコード変更なしに分散可能

## セットアップ

### 前提条件

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Vertex AI APIが有効なGoogle Cloudプロジェクト
- ADC設定済み: `gcloud auth application-default login`

### インストール

```bash
uv sync
```

### 設定

```bash
export VR_PROJECT_ID=your-gcp-project-id
# オプション:
# export VR_LOCATION=asia-northeast1
# export VR_MODEL_INTAKE=gemini-2.5-pro
# export VR_MODEL_ORCHESTRATOR=gemini-2.5-flash
```

## 使い方

### 1. 規定文書を専門家定義にコンパイル

```bash
vr-compile --output-dir profiles/ < sample/regulations.md
```

### 2. レビューパイプラインの実行

```bash
# 1パス目 — 追加質問が生成される場合がある
cat sample/application.json \
  | vr-intake --profiles-dir profiles/ \
  > workspace/intake_output.json

# 申請者向けQ&Aシートを生成
cat workspace/intake_output.json | vr-questions > workspace/qa_sheet.md

# 申請者が回答を記入した後、2パス目を実行
cat workspace/intake_output.json \
  | vr-answers workspace/qa_sheet_filled.md \
  | vr-intake --profiles-dir profiles/ \
  > workspace/intake_final.json

# 専門家評価と最終判定を実行
cat workspace/intake_final.json \
  | vr-orchestrate --profiles-dir profiles/ \
  | vr-brain \
  | tee workspace/assessment.json \
  | vr-report > workspace/report.md
```

### ワンショットE2Eテスト

```bash
bash scripts/e2e.sh
```

## ドキュメント

- [アーキテクチャ](docs/design/architecture.md) — システム設計全体、モジュール仕様、データ構造定義

## ライセンス

MIT
