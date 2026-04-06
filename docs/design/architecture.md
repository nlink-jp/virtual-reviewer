# Architecture — virtual-reviewer

## Core Thesis

セキュリティレビューにおけるRAGの限界は「質問と文書の表層的な類似度」
に依存する点にある。否定・例外条件の見落とし、複数規定の横断的判定、
暗黙の前提の欠落 —— これらはすべて検索精度の問題に帰着する。

virtual-reviewer はこの限界を **検索をなくす** ことで突破する。
規定文書をオーサリング時に専門家単位で構造化し、各専門家モデルが
担当規定の全文をコンテキストとして保持する。検索に依存しないため、
否定条件も例外も漏れない。

**要するに: RAGの「検索して引用する」から、専門家が「規定を能動的に
適用する」へのパラダイムシフト。**

---

## Design Philosophy

UNIX 哲学に従う。

1. **各モジュールは1つのことをうまくやる** — intake は構造化、expert は判定、brain は統合。それ以外のことはしない
2. **データは stdout、ログは stderr** — モジュール間は JSON を標準入出力で受け渡す。ログは stderr に JSONL で出力し、コレクタに任せる
3. **パイプで繋がる** — モジュールの結合はシェルパイプと同じ感覚で行える

```bash
# フルパイプライン
cat application.json \
  | vr-intake --profiles-dir profiles/ \
  | vr-orchestrate --profiles-dir profiles/ \
  | vr-brain \
  | tee assessment.json \
  | vr-report > report.md

# 個別実行・デバッグも自然にできる
cat application.json | vr-intake --profiles-dir profiles/ > intake_output.json
cat intake_output.json | jq '.record.confidence'

# 追加質問がある場合は Q&A シートを生成
cat intake_output.json | vr-questions > qa_sheet.md
# → 申請者が回答を記入
cat intake_output.json | vr-answers qa_sheet_filled.md \
  | vr-intake --profiles-dir profiles/ > intake_final.json
```

この設計により:

- **テストが容易** — 各モジュールに固定の JSON を食わせて出力を検証するだけ
- **デバッグが容易** — パイプラインの任意の段階で中間データを `jq` で確認できる
- **差し替えが容易** — インターフェース（JSON スキーマ）さえ守れば、実装言語もモデルも自由に変えられる
- **段階的に構築できる** — まず1モジュールだけ作って動かし、順に繋げていける
- **分散実行が自然にできる** — SSH 越しにリモートマシンでモジュールを実行しても、パイプラインは同じ

```bash
# SSH による分散実行 — モジュールのコードは一切変更不要
# intake だけ GPU マシンで動かす（マルチモーダル処理が重い場合）
cat application.json | ssh gpu-node vr-intake --profiles-dir profiles/ \
  | vr-orchestrate --profiles-dir profiles/ | vr-brain > assessment.json
```

各モジュールは自分がローカルで動いているかリモートで動いているかを知らない。
stdin から読み、stdout に書き、stderr にログを吐く。それだけを守れば、
SSH がそのまま分散実行基盤になる。特別な RPC フレームワークもメッセージキューも不要。

---

## System Overview

AI（LLM）を活用したセキュリティレビューシステム。申請者からの
レビュー依頼（プレゼン資料・仕様書等）を受け取り、組織のセキュリティ
規定に基づいてリスク分析・要件充足性の判定・根拠の構造的提示を行う。

人間のレビュワーを補助・代替し、定型的な一次評価を自動化することで、
人間がより高度で複雑な案件に集中できる環境を構築する。

---

## Module Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       virtual-reviewer                           │
│                                                                 │
│  ┌───────────────────┐  ┌────────────────────────────────────┐  │
│  │ vr-compile         │  │ Runtime Pipeline                  │  │
│  │ (offline)          │  │                                    │  │
│  │ 規定.md → 専門家    │  │  vr-intake ──→ vr-orchestrate     │  │
│  │ 定義群 (.json)     │  │       │              │            │  │
│  └───────────────────┘  │       ▼              ▼            │  │
│                          │  vr-questions    vr-brain         │  │
│  LLM を使わないモジュール  │  (Q&Aシート)        │            │  │
│  ┌───────────────────┐  │       │              ▼            │  │
│  │ vr-questions       │  │  vr-answers     vr-report        │  │
│  │ vr-answers         │  │  (2パス目)      (日本語MD)       │  │
│  │ vr-report          │  └────────────────────────────────────┘  │
│  └───────────────────┘                                           │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │ Infrastructure: Google Cloud Vertex AI API (google-genai SDK)││
│  └──────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Module 一覧

| コマンド | 役割 | LLM | 入力 (stdin) | 出力 (stdout) |
|---------|------|-----|-------------|--------------|
| `vr-compile` | 規定 Markdown → 専門家定義 | Yes | 規定文書 | — (ファイル出力) |
| `vr-intake` | 申請資料 → 構造化データ（2パスQ&A） | Yes | IntakeInput | IntakeOutput |
| `vr-orchestrate` | 専門家に並列配信、判定収集 | Yes | IntakeOutput / ApplicationRecord | ExpertVerdict[] |
| `vr-brain` | 矛盾解消、総合判定 | Yes | ExpertVerdict[] | FinalAssessment |
| `vr-report` | 最終判定 → 日本語Markdownレポート | No | FinalAssessment | Markdown |
| `vr-questions` | 追加質問 → Q&Aシート | No | IntakeOutput | Markdown |
| `vr-answers` | 記入済みQ&A → 2パス目入力 | No | IntakeOutput + Q&A.md | IntakeInput |

### Module 0: Intake Processor — 申請受付・構造化

申請者が提出した多様な形式の資料をマルチモーダルLLMで解析し、
構造化された申請データ（`ApplicationRecord`）に変換する。

単なる変換器ではなく、**対話的な情報収集エージェント**として機能し、
不足情報や低確信度の項目について申請者に追加情報を求める。

#### 入力

- PowerPoint / Google Slides（システム構成図、データフロー図）
- Word / PDF（提案書、仕様書）
- Excel（要件一覧、比較表）
- 自由記述テキスト

#### 処理フェーズ（2パス構成）

Intake は純粋関数として設計されており、対話ループは外部で制御する。

```
1パス目: IntakeInput(materials=[...], answers=null)
  → マルチモーダルLLM → IntakeOutput(record={ドラフト}, questions=[...])
  → questions が空でなければ vr-questions で Q&A シート生成
  → 申請者が回答を記入

2パス目: IntakeInput(materials=[...], answers=[{回答群}])
  → マルチモーダルLLM → IntakeOutput(record={最終版}, questions=[])
  → questions が空 → パイプラインに流せる
```

```bash
# 実際の実行フロー
cat application.json | vr-intake --profiles-dir profiles/ > intake_output.json
cat intake_output.json | vr-questions > qa_sheet.md
# → 申請者が記入
cat intake_output.json | vr-answers qa_sheet_filled.md \
  | vr-intake --profiles-dir profiles/ > intake_final.json
```

#### 精度担保ロジック

| パターン | 例 | アクション |
|---------|---|-----------|
| 必須フィールド欠損 | データフロー図がない | 資料の追加提出を要求 |
| 曖昧な記述 | 「適切な認証を行う」 | 具体的な方式を質問 |
| 資料間の矛盾 | 構成図と説明文の不一致 | どちらが正か確認 |
| 推測で補完した箇所 | 図からIPレンジを読み取ったが不鮮明 | 確認を求める |
| 判定に影響する未言及事項 | 個人情報を扱うのに暗号化の記載なし | 意図的な省略か確認 |

「未言及事項の検出」は、専門家モデルの `required_fields` を先行参照
することで実現する。これにより、インテークの段階で後段の情報要件を
満たす品質が担保される。

#### 設計要件

- マルチモーダル対応: `google-genai` SDK の `Part.from_bytes()` で画像・PDF を直接解析
- 構造化出力: Vertex AI `response_schema` で Pydantic モデル (`IntakeOutput`) を強制
- 2パス設計: モジュール自体は純粋関数。対話ループは `vr-questions` / `vr-answers` で外部化
- 専門家の `required_fields` を参照し、不足情報を事前検出
- 全テキスト出力は日本語

#### 使用モデル

`gemini-2.5-pro` — マルチモーダル性能と日本語能力が必須要件であるため。

---

### Module 1: Persona Compiler — 専門家定義生成

規定文書（Markdown）を意味単位で分解し、各専門家モデルの定義
（システムプロンプト + 担当規定 + メタデータ）を生成する
オフラインのコンパイルパイプライン。

規定の改訂時にのみ実行される。リクエスト時処理ではない。

#### 入力

Markdown 形式の規定文書。ヘッダ階層（`##`, `###`）を意味境界として利用する。

```markdown
# セキュリティ規定

## 第1章 認証・アクセス制御
### 1.1 認証方式の要件
...
### 1.2 多要素認証の適用基準
...

## 第2章 データ保護
### 2.1 暗号化要件
...
```

#### 出力

専門家単位で2つの成果物を生成する:

**1. ExpertProfile（専門家定義）**

各専門家モデルのシステムプロンプト、担当規定の全文、
`ApplicationRecord` のどのフィールドを参照するかの宣言。

**2. RequiredFieldsSchema（必要情報スキーマ）**

この専門家が判定を行うために `ApplicationRecord` に
含まれていなければならないフィールドの一覧。
Module 0（Intake Processor）が Phase 2 の検証に使用する。

#### 分解戦略

```
規定文書（Markdown）
  └─ 章単位で分割 → 1章 = 1専門家
       ├─ 本文（判定基準そのもの）
       ├─ 適用条件（どんな案件に適用されるか）
       ├─ 判定ロジック（合否の閾値・条件）
       ├─ 過去適用事例へのリンク（蓄積に応じて追加）
       └─ 必要情報スキーマ（判定に必要な ApplicationRecord フィールド）
```

#### 設計要件

- 規定のデプロイパイプラインとして機能する（改訂 → コンパイル → デプロイ）
- 専門家1体あたりのコンテキストサイズが対象モデルのウィンドウに収まることを検証
- 規定のバージョン管理と専門家定義のバージョンを紐づけ

#### 使用モデル

`gemini-2.5-pro` — 文書構造の理解とメタデータ抽出。
オフライン処理のためレイテンシ要件は緩い。

---

### Module 2: Orchestrator — 実行制御

構造化された申請データ（`ApplicationRecord`）を受け取り、
適切な専門家モデル群に配信し、各専門家の判定結果
（`ExpertVerdict`）を収集して Brain Unit に引き渡す。

#### 処理フロー

```
ApplicationRecord
  │
  ├─ 専門家数が少ない場合 → 全専門家に並列配信（単純・確実）
  │
  └─ 専門家数が多い場合 → プランナーが選別して配信（コスト最適化）
       │
       ├─ ExpertProfile.required_fields と ApplicationRecord の
       │  フィールド有無を突き合わせ、関連する専門家を絞り込む
       │
       └─ 各専門家の domain サマリーを参照し、申請内容との
          関連度を判定
```

#### 専門家モデルの実行

各専門家は以下の入力を受け取り、`ExpertVerdict` を出力する:

- システムプロンプト（ExpertProfile.system_prompt）
- 担当規定の全文（ExpertProfile に内包）
- 申請データ（ApplicationRecord）のうち、自身の required_fields に該当する部分

専門家は **検索を行わない**。規定全文がコンテキストに存在するため、
否定条件・例外条件・暗黙の前提も含めて判定できる。

#### 設計要件

- 並列実行: 専門家モデルは互いに独立しており、並列に API 呼び出し可能
- タイムアウト: 各専門家に応答タイムアウトを設定（デフォルト 60 秒）
- リトライ: API エラー時のリトライポリシー（指数バックオフ、最大 3 回）
- プランナー判断の自信度: 閾値以下の場合、全専門家にフォールバック配信

#### 使用モデル

- プランナー / ルーティング: `gemini-2.5-flash` — 軽量で高速
- 専門家モデル: `gemini-2.5-pro` — 長コンテキスト、規定の厳密な適用

---

### Module 3: Brain Unit — 最終判定

全専門家の判定結果（`ExpertVerdict[]`）を統合し、矛盾の解消、
リスクの重み付け、総合判定を行う。単なる集約ではなく、
高度な推論を要するモジュール。

#### 責務

1. **矛盾検出と解消**: 専門家 A が「許可」、専門家 B が「禁止」と
   判定した場合の衝突を検出し、規定の優先順位に基づいて解消する
2. **リスク重み付け**: 全項目合格でも組み合わせとして総合リスクが
   高い場合を検出する（例: 個別には許容範囲だが、集積すると危険）
3. **判定根拠の構造化**: 人間レビュワーが検証可能な形式で、
   判定→根拠規定→対象フィールド→元資料の追跡チェーンを提示する
4. **条件付き承認の生成**: 「Xを是正すれば承認可」の条件を具体的に提示

#### 処理フロー

```
ExpertVerdict[] (全専門家の判定)
  │
  ├─ 1. 矛盾検出
  │     同一 target_field に対する複数専門家の判定を突き合わせ
  │
  ├─ 2. 矛盾解消
  │     規定の優先順位、severity の比較、条件の包含関係で解消
  │
  ├─ 3. リスク集約
  │     severity ごとの件数集計 + 組み合わせリスクの評価
  │
  ├─ 4. 総合判定
  │     approved / rejected / conditional の決定
  │
  └─ 5. FinalAssessment 生成
        判定 + 根拠チェーン + 条件 + 監査証跡
```

#### 設計要件

- 構造化データ間の推論が主務のため、マルチモーダル性能は不要
- 判定の再現性が求められるため、temperature は低く設定（0.0〜0.2）
- 判定ロジックの一部はルールベース（severity の集計等）で実装し、
  LLM には矛盾解消と総合評価のみを委ねることでハルシネーションリスクを低減

#### 使用モデル

`gemini-2.5-pro` — 高度な推論力が必要。
構造化データのみを扱うため、将来的にモデル変更の余地あり。

---

## Data Structure Definitions

モジュール間は自然言語ではなく、以下の構造化データで受け渡す。
これにより情報の欠落・解釈のブレを防ぎ、監査証跡を機械的に生成できる。

### ApplicationRecord (Module 0 → Module 2)

インテークプロセッサが生成する、構造化された申請データ。

```yaml
ApplicationRecord:
  type: object
  required:
    - application_id
    - submitted_at
    - applicant
    - system_overview
    - data_flows
    - services
  properties:
    application_id:
      type: string
      description: 申請の一意識別子
    submitted_at:
      type: string
      format: date-time
    applicant:
      type: object
      properties:
        name:
          type: string
        department:
          type: string
        contact:
          type: string
    system_overview:
      type: string
      description: システムの概要説明
    data_flows:
      type: array
      items:
        type: object
        properties:
          src:
            type: string
            description: データの送信元
          dst:
            type: string
            description: データの送信先
          data_type:
            type: string
            description: データの種類
          classification:
            type: string
            enum: [public, internal, confidential, restricted]
            description: データの機密区分
    services:
      type: array
      items:
        type: object
        properties:
          name:
            type: string
          vendor:
            type: string
          hosting:
            type: string
            enum: [saas, iaas, paas, on-premise, hybrid]
          auth_method:
            type: string
            description: 認証方式
    data_stores:
      type: array
      items:
        type: object
        properties:
          type:
            type: string
            description: ストレージの種類
          encryption:
            type: string
            enum: [at-rest, in-transit, both, none]
          location:
            type: string
            description: データ保存先のリージョン/ロケーション
          retention:
            type: string
            description: データ保持期間
    confidence:
      type: object
      description: 各フィールドの確信度スコア（0.0〜1.0）
      additionalProperties:
        type: number
    unresolved:
      type: array
      description: Phase 2 での対話ログ
      items:
        type: object
        properties:
          field:
            type: string
          question:
            type: string
          response:
            type: string
          resolved:
            type: boolean
```

### ExpertProfile (Module 1 → Module 2)

ペルソナコンパイラが生成する専門家の定義。

```yaml
ExpertProfile:
  type: object
  required:
    - expert_id
    - domain
    - system_prompt
    - regulation_text
    - required_fields
    - regulation_refs
  properties:
    expert_id:
      type: string
      description: 専門家の一意識別子
    domain:
      type: string
      description: 担当領域（例 "認証・アクセス制御"）
    system_prompt:
      type: string
      description: 専門家モデルに与えるシステムプロンプト
    regulation_text:
      type: string
      description: 担当規定の全文（コンテキストに載せる）
    required_fields:
      type: array
      items:
        type: string
      description: >
        ApplicationRecord のうち、この専門家が判定に必要とする
        フィールドパスの一覧（例 ["services[].auth_method", "data_flows"]）
    regulation_refs:
      type: array
      items:
        type: object
        properties:
          section_id:
            type: string
            description: 規定のセクションID（例 "1.2"）
          title:
            type: string
            description: セクションタイトル
    version:
      type: string
      description: 元となった規定文書のバージョン
```

### ExpertVerdict (Module 2 → Module 3)

各専門家モデルが出力する判定結果。

```yaml
ExpertVerdict:
  type: object
  required:
    - expert_id
    - verdict
    - findings
    - confidence
  properties:
    expert_id:
      type: string
    verdict:
      type: string
      enum: [pass, fail, conditional, insufficient_info]
      description: この専門家の総合判定
    findings:
      type: array
      items:
        type: object
        required:
          - regulation_ref
          - target_field
          - severity
          - finding
        properties:
          regulation_ref:
            type: string
            description: 根拠となる規定のセクションID
          target_field:
            type: string
            description: >
              ApplicationRecord のどのフィールドに対する指摘か
              （例 "services[0].auth_method"）
          severity:
            type: string
            enum: [critical, high, medium, low, info]
          finding:
            type: string
            description: 指摘内容
          recommendation:
            type: string
            description: 推奨対策
    confidence:
      type: number
      minimum: 0.0
      maximum: 1.0
      description: この判定全体の確信度
```

### FinalAssessment (Module 3 → Output)

Brain Unit が出力する最終判定。

```yaml
FinalAssessment:
  type: object
  required:
    - assessment_id
    - application_id
    - overall_verdict
    - risk_summary
    - findings
    - evidence_chain
  properties:
    assessment_id:
      type: string
      description: 判定の一意識別子
    application_id:
      type: string
      description: 対応する申請ID
    assessed_at:
      type: string
      format: date-time
    overall_verdict:
      type: string
      enum: [approved, rejected, conditional]
    conditions:
      type: array
      items:
        type: string
      description: conditional の場合の承認条件
    conflicts:
      type: array
      description: 専門家間で検出された矛盾とその解消
      items:
        type: object
        properties:
          expert_a:
            type: string
          expert_b:
            type: string
          target_field:
            type: string
          description:
            type: string
          resolution:
            type: string
    risk_summary:
      type: object
      properties:
        critical:
          type: integer
        high:
          type: integer
        medium:
          type: integer
        low:
          type: integer
        info:
          type: integer
    findings:
      type: array
      description: 全専門家の findings を統合・重複排除したもの
      items:
        $ref: "#/ExpertVerdict/properties/findings/items"
    evidence_chain:
      type: array
      description: 判定過程の監査証跡
      items:
        type: object
        properties:
          step:
            type: integer
          module:
            type: string
            description: 処理を行ったモジュール名
          input_hash:
            type: string
            description: 入力データの SHA-256 ハッシュ
          output_hash:
            type: string
            description: 出力データの SHA-256 ハッシュ
          timestamp:
            type: string
            format: date-time
    model_versions:
      type: object
      description: 判定に使用された各モデルのバージョン
      additionalProperties:
        type: string
```

---

## Data Flow

```
                    ┌────────────────────┐
                    │   規定文書 (.md)    │
                    └────────┬───────────┘
                             │ (改訂時のみ)
                             ▼
                    ┌────────────────────┐
                    │    vr-compile      │ オフライン
                    └──┬──────────┬──────┘
                       │          │
          ExpertProfile[]    required_fields
                       │          │
                       ▼          │
              ┌────────────┐      │
              │  profiles/  │      │
              └─────┬──────┘      │
                    │             │
  ┌─────────┐      │             │
  │ 申請資料 │      │             ▼
  │ (多様な  │    ┌─┴─────────────────────┐
  │  形式)   │───→│      vr-intake        │ 1パス目
  │          │    │   (multimodal LLM)     │
  └─────────┘    └──────────┬─────────────┘
                            │ IntakeOutput
                   ┌────────┤
                   │        │ (questions が空なら直接↓へ)
                   ▼        │
            ┌─────────────┐ │
            │ vr-questions │ │
            │ (Q&Aシート)  │ │
            └──────┬──────┘ │
                   ▼        │
            ┌─────────────┐ │
            │ 申請者が回答  │ │
            └──────┬──────┘ │
                   ▼        │
            ┌─────────────┐ │
            │ vr-answers   │ │
            └──────┬──────┘ │
                   ▼        │
            ┌─────────────┐ │
            │ vr-intake    │ │  2パス目
            │ (2nd pass)   │ │
            └──────┬──────┘ │
                   │        │
                   └───┬────┘
                       ▼
              ┌────────────────────┐
              │   vr-orchestrate   │
              │                    │
              │  ┌──┐ ┌──┐ ┌──┐   │
              │  │E1│ │E2│ │E3│   │  並列実行
              │  └──┘ └──┘ └──┘   │
              └────────┬───────────┘
                       │ ExpertVerdict[]
                       ▼
              ┌────────────────────┐
              │     vr-brain       │
              │                    │
              │  矛盾検出・解消     │
              │  リスク重み付け     │
              │  総合判定           │
              └────────┬───────────┘
                       │ FinalAssessment
                  ┌────┴────┐
                  ▼         ▼
           ┌──────────┐ ┌──────────────┐
           │ vr-report │ │ assessment   │
           │ (日本語MD)│ │ .json        │
           └──────────┘ └──────┬───────┘
                               ▼
                      ┌────────────────┐
                      │ Human Reviewer │
                      │ (最終承認/修正) │
                      └────────────────┘
```

---

## Infrastructure

### LLM API

Google Cloud Vertex AI API に統一。SDK は `google-genai` を使用する。

```python
# クライアント初期化 — ADC で自動認証
from google import genai
client = genai.Client(
    vertexai=True,
    project=os.environ["VR_PROJECT_ID"],
    location=os.environ.get("VR_LOCATION", "asia-northeast1"),
)
```

モデルは環境変数で切り替え可能（コード変更不要）:

```bash
export VR_PROJECT_ID=my-project
export VR_LOCATION=asia-northeast1        # デフォルト
export VR_MODEL_INTAKE=gemini-2.5-pro     # デフォルト
export VR_MODEL_ORCHESTRATOR=gemini-2.5-flash  # デフォルト
export VR_MODEL_EXPERT=gemini-2.5-pro     # デフォルト
export VR_MODEL_BRAIN=gemini-2.5-pro      # デフォルト
```

LLM 出力の品質保証には Vertex AI の `response_schema` を使用し、
Pydantic モデルで出力スキーマを強制する。これにより LLM がフィールド名を
間違える問題（例: `src` vs `source`）を構造的に排除する。

- Vertex AI 経由で Claude 等の他モデルも利用可能（API 変更なし）
- レート制限時は指数バックオフで自動リトライ（最大 3 回）

### Authentication

Application Default Credentials (ADC) を使用する。

- **ローカル実験時**: `gcloud auth application-default login` によるユーザー認証
- **クラウドデプロイ時**: アタッチされたサービスアカウントが自動で使用される
- **コード側の変更は不要**: ADC がランタイム環境に応じて自動的に認証情報を解決する

```bash
# ローカル実験時
gcloud auth application-default login

# クラウドデプロイ時は何もしない — サービスアカウントが自動で使われる
```

### Security

- VPC Service Controls によるデータ境界制御（本番デプロイ時）
- 規定文書・申請データは指定リージョン内で処理

### Model Version Management

- モデルバージョンを設定ファイルで固定
- バージョン更新時はリグレッションテストを実施
- FinalAssessment に使用モデルバージョンを記録（判定の再現性確保）

---

## Feedback Loop

人間レビュワーの修正結果をシステムにフィードバックする仕組み。

```
FinalAssessment
  → 人間レビュワーが確認
  → 修正・追記・却下
  → ReviewerFeedback として蓄積
      ├─ 判定の修正内容
      ├─ 修正理由
      └─ 対象の規定セクション

蓄積されたフィードバック:
  → Persona Compiler が「過去適用事例」として専門家定義に追加
  → Brain Unit の矛盾解消ロジックの改善に活用
  → 精度 KPI（適合率・再現率）の計測に使用
```

---

## Non-Functional Requirements

### Performance

| 指標 | 目標値 |
|-----|-------|
| Intake Processor 応答時間 | 30 秒以内（Phase 1 のみ） |
| 専門家モデル 1 体あたりの応答時間 | 60 秒以内 |
| エンドツーエンド（申請→最終判定） | 5 分以内（対話なし時） |
| 同時処理可能な申請数 | 10 件以上 |

### Availability

| 指標 | 目標値 |
|-----|-------|
| システム稼働率 | 99.5%（業務時間帯） |
| Vertex AI API 障害時 | キューイングして復旧後に再処理 |

### Logging

各モジュールは構造化 JSON ログを **stderr** に出力する。
stdout はデータパスとして予約されているため、ログは stderr に分離する。
ログの収集・保存・転送はログコレクタ（Cloud Logging, Fluentd 等）に委ねる。
モジュール自身はログの宛先を知らない。

#### ログフォーマット

```json
{
  "timestamp": "2026-04-06T16:22:41.111231+00:00",
  "severity": "INFO",
  "module": "expert",
  "event": "llm_request",
  "message": "Calling gemini-2.5-pro",
  "model": "gemini-2.5-pro",
  "temperature": 0.1
}
{
  "timestamp": "2026-04-06T16:23:30.253557+00:00",
  "severity": "INFO",
  "module": "orchestrator",
  "event": "output",
  "message": "Writing ExpertVerdict[] to stdout",
  "input_hash": "sha256:e6c587c176b10371",
  "output_hash": "sha256:c909f83926f1a0ee"
}
```

#### 設計方針

- **stderr のみに出力**: stdout はデータ、stderr はログ。ファイル書き込み・ネットワーク送信はモジュールの責務外
- **1イベント1行**: 改行区切りの JSON Lines (JSONL) 形式
- **共通フィールド**: `timestamp`, `severity`, `module`, `application_id` は全ログに必須
- **evidence_chain との統合**: `input_hash` / `output_hash` をログに含めることで、
  FinalAssessment の evidence_chain とログが相互参照可能
- **ローカル実験時**: stderr がそのままターミナルに流れる。`2>&1 | jq` でフィルタ可能
- **本番デプロイ時**: ログコレクタが stderr を拾い、Cloud Logging 等に転送

### Auditability

- 全モジュール間のデータ受け渡しにハッシュチェーンを記録
- FinalAssessment から元の申請資料まで追跡可能
- 判定に使用したモデルバージョン・規定バージョンを記録
- evidence_chain により判定過程の改竄検知が可能

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| LLM API | Vertex AI 統一 (`google-genai` SDK) | エンドポイント・認証・ログが1系統。旧 `vertexai` SDK は deprecated |
| 出力スキーマ強制 | `response_schema` (Pydantic) | LLM のフィールド名ブレを構造的に排除 |
| 検索方式 | RAG を使わない | 検索精度の上限がシステムの上限になる問題を回避。専門家が規定全文を保持 |
| モジュール間通信 | 構造化データ (JSON) | 自然言語の曖昧性・情報欠落を排除。監査証跡が機械的に生成可能 |
| 専門家の粒度 | 規定の章単位 | Markdown のヘッダ階層と対応。1モデルのコンテキストウィンドウに収まる単位 |
| オーケストレーション | 全専門家に並列配信 | PoC では専門家数が少ないため単純方式。将来的にプランナー選別を追加可能 |
| Intake の対話 | 2パス構成 + Q&Aシート | モジュールは純粋関数。対話ループは `vr-questions` / `vr-answers` で外部化 |
| Brain Unit の温度 | 0.1 | 判定の再現性を優先。創造性は不要 |
| 一部ロジックのルールベース化 | severity 集計等 | LLM のハルシネーションリスクを限定的にする |
| 出力言語 | 全テキスト日本語 | 規定・申請が日本語。プロンプトで日本語出力を指示 |
| LLM 不使用モジュール | vr-report, vr-questions, vr-answers | テンプレート変換は LLM 不要。コストゼロ・即時実行 |

---

## Future Directions

- **申請フォームUI**: Web ベースの申請フォーム + ファイルアップロード
- **ダッシュボード**: レビュー案件の一覧・進捗・統計の可視化
- **ナレッジベース管理UI**: 規定文書の編集・バージョン管理・コンパイル実行
- **類似案件リコメンド**: 過去の申請と FinalAssessment を基に類似案件を提示
- **段階的導入**: 低リスク案件（SaaS 利用申請等）から適用範囲を拡大
- **精度モニタリング**: 人間レビュワーの修正率を KPI として継続計測
