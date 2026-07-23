# Agent Risk Lab

Agent Risk Labは、registryへ登録した実験入力を、明示したProvider・モデル・防御プロファイルで実行する実験基盤です。

現在はGemini Interactions APIに対応し、次の入力・実験を扱います。

- UTF-8テキスト
- inline PDF
- 登録fixtureを一時shadowへ複製して行う、限定的な`file_copy`

dry-runが既定であり、`--live`を明示しない限り外部API通信は行いません。

## 現在の構成

```text
trial_prompt_injection/
├── configs/
│   ├── base_system_prompt.txt
│   ├── profiles/
│   │   ├── registry.toml
│   │   ├── baseline/v1/profile.toml
│   │   └── hardened/v1/profile.toml
│   ├── providers/
│   │   └── gemini.toml
│   └── targets/
│       └── gemini_3_1_flash_lite.toml
├── data/
│   └── experiments/
│       ├── registry.toml
│       ├── EXP-ABE-URL/
│       │   └── prompt.txt
│       ├── EXP-PDF-SUMMARY/
│       │   ├── prompt.txt
│       │   └── ut-vision2030-jp.pdf
│       └── EXP_FILE_COPY/
│           ├── prompt.txt
│           └── fixture/
│               ├── archive/.gitkeep
│               └── documents/source.txt
├── src/
│   └── agent_risk_lab/
│       ├── core/
│       ├── evaluators/
│       ├── experiments/
│       └── providers/
│           ├── base.py
│           └── gemini/
│               ├── __init__.py
│               ├── client.py
│               └── models.py
├── tests/
├── AGENTS.md
├── pyproject.toml
└── README.md
```

各領域の責務は次のとおりです。

- `configs/base_system_prompt.txt`: 全実験に共通する基本システム指示
- `configs/profiles/`: バージョン管理された共通防御プロファイル
- `configs/providers/`: Provider共通設定
- `configs/targets/`: Providerとモデルの実行可能な組合せ
- `data/experiments/`: registryへ登録する実験入力
- `src/agent_risk_lab/providers/`: Provider固有のPython実装
- `artifacts/logs/`: live実行のrawログ。Git管理外

現在の実装には、旧サンプルの`run`、`batch`、`file-run`、`fs-shadow-run`は含まれません。ファイル操作は登録済み`fs_shadow`実験から要求された`file_copy`だけに限定され、汎用shell、削除、移動、上書き、外部送信は実装していません。

## 必要環境

- Git
- Python 3.12以上
- live実行を行う場合のみGemini APIキー

macOS/Linuxのコマンド例を示します。Windowsでは`.venv/bin/`を`.venv\Scripts\`に読み替えてください。

## cloneとセットアップ

```console
git clone <repository-url>
cd trial_prompt_injection
python3.12 -m venv .venv
.venv/bin/python -m pip install '.[dev]'
```

Providerごとに仮想環境を作らず、リポジトリルートの`.venv`を共通環境として使用します。activateは任意です。以降の例ではclone先に依存しない相対パスを使用します。

環境を確認します。

```console
.venv/bin/python -c "import sys; print(sys.executable); print(sys.prefix)"
.venv/bin/python -m pip show pytest google-genai
.venv/bin/agent-risk-lab doctor
.venv/bin/python -m pytest -q
```

`doctor`が`"ok": true`を返し、pytestが成功すれば準備完了です。

## Providerとtarget

Provider設定とモデル設定は分離されています。

```text
configs/providers/gemini.toml
configs/targets/gemini_3_1_flash_lite.toml
```

現在のtargetは次の1件です。

```text
target_id:  gemini_3_1_flash_lite
provider:   gemini
adapter:    gemini
model:      gemini-3.1-flash-lite
```

実行時は生のモデル名ではなく、登録済みtargetを指定します。

```console
.venv/bin/agent-risk-lab experiment-run EXP-ABE-URL \
  --target gemini_3_1_flash_lite \
  --profile baseline
```

`--target`省略時は互換性のため`gemini_3_1_flash_lite`が選択されますが、非推奨警告が表示されます。自由なモデル名を指定する`--model`はありません。

Providerを追加する場合は、次を追加します。

- `configs/providers/<provider-id>.toml`
- `src/agent_risk_lab/providers/<provider-id>/`
- 対応する`configs/targets/<target-id>.toml`

同じProviderでモデルだけを追加する場合は、Pythonパッケージを増やさずtarget設定を追加します。Gemini SDKとInteractions APIの処理は`src/agent_risk_lab/providers/gemini/client.py`だけに配置されています。

## プロファイル

プロファイルは次の形式で保存します。

```text
configs/profiles/<name>/v<version>/profile.toml
```

`configs/profiles/registry.toml`の`latest`が、バージョン省略時に使用する公開済み最新版です。

```console
.venv/bin/agent-risk-lab experiment-run EXP-ABE-URL \
  --target gemini_3_1_flash_lite \
  --profile hardened
```

公開済みの過去バージョンは明示できます。

```console
.venv/bin/agent-risk-lab experiment-run EXP-ABE-URL \
  --target gemini_3_1_flash_lite \
  --profile hardened \
  --profile-version 1
```

公開済みバージョンは上書きせず、変更時は新しいバージョンを作成してください。現在の`baseline` v1と`hardened` v1はfragmentが空で、意図的に同じ実効システムプロンプトを生成します。hardened v2以降はまだ存在しません。

## 実験registry

実験は`data/experiments/<experiment-id>/`へ保存します。`data/experiments/registry.toml`への登録自体が実行許可です。

実行前に次を検証します。

- experiment IDがregistryに存在する
- `enabled = true`
- 入力ファイルが存在する
- 入力が`data/experiments/`内にある
- 絶対パス、`..`、symlink、特殊ファイルではない
- 入力形式とregistryの`type`が一致する
- 実ファイルのSHA-256が登録値と一致する
- テキストはUTF-8で、PDFは正常なPDFかつ10MB以下

いずれかが不正な場合は、APIを呼び出す前に停止します。registry未登録のファイルは実行できません。入力を変更した場合は内容を再確認し、SHA-256を明示的に更新してください。

## 登録済み実験を確認する

```console
.venv/bin/agent-risk-lab list-experiments
.venv/bin/agent-risk-lab show-experiment EXP-ABE-URL
.venv/bin/agent-risk-lab show-experiment EXP-PDF-SUMMARY
.venv/bin/agent-risk-lab show-experiment EXP_FILE_COPY
.venv/bin/agent-risk-lab list-profiles
.venv/bin/agent-risk-lab show-profile baseline
```

現在の登録済み実験は次の3件です。

- `EXP-ABE-URL`: 単一テキスト入力
- `EXP-PDF-SUMMARY`: 指示テキストとPDFの複数入力
- `EXP_FILE_COPY`: 一時shadow内で1ファイルだけを複製する正常系実験

## 単一テキスト実験を作成する

実験ディレクトリとUTF-8のプロンプトを作成します。

```console
mkdir -p data/experiments/EXP-MY-001
```

`data/experiments/EXP-MY-001/prompt.txt`へ実験内容を記述します。APIキー、実在する秘密情報、credentials、不要な個人情報は保存しないでください。

SHA-256をバイト単位で計算します。

```console
.venv/bin/python -c "import hashlib, pathlib; p=pathlib.Path('data/experiments/EXP-MY-001/prompt.txt'); print(hashlib.sha256(p.read_bytes()).hexdigest())"
```

`data/experiments/registry.toml`へ登録します。

```toml
[[experiments]]
id = "EXP-MY-001"
type = "prompt"
description = "Describe this experiment."
prompt_file = "EXP-MY-001/prompt.txt"
prompt_sha256 = "<calculated-sha256>"
enabled = true
```

`prompt_file`と`prompt_sha256`は、既存の単一入力形式として利用できます。

## 複数入力・PDF実験を作成する

`EXP-PDF-SUMMARY`は次の構成です。

```text
data/experiments/EXP-PDF-SUMMARY/
├── prompt.txt
└── ut-vision2030-jp.pdf
```

`prompt.txt`はPDFに対する指示、PDFは評価対象文書です。PDFのファイル名は任意で、`prompt.pdf`や`document.pdf`に固定する必要はありません。registryの`file`を実ファイル名と一致させます。

ディレクトリ直下の全ファイルについて、1回のコマンドで個別のSHA-256を計算できます。

```console
.venv/bin/python -c "import hashlib, pathlib; root=pathlib.Path('data/experiments/EXP-PDF-SUMMARY'); [print(f'{p.name} = {hashlib.sha256(p.read_bytes()).hexdigest()}') for p in sorted(root.iterdir()) if p.is_file()]"
```

複数ファイルを1つのハッシュへまとめるのではなく、各入力に個別のSHA-256を登録します。

```toml
[[experiments]]
id = "EXP-PDF-SUMMARY"
type = "prompt"
description = "Summarize a registered PDF document."
enabled = true

[[experiments.inputs]]
type = "text"
file = "EXP-PDF-SUMMARY/prompt.txt"
sha256 = "<prompt.txt-sha256>"

[[experiments.inputs]]
type = "document"
file = "EXP-PDF-SUMMARY/ut-vision2030-jp.pdf"
sha256 = "<ut-vision2030-jp.pdf-sha256>"
```

`inputs`は1件だけでも使用でき、記載順で1回のInteractions APIリクエストへ渡されます。1つの実験で`inputs`と旧単一入力形式を同時には指定できません。

- `type = "text"`: UTF-8テキスト
- `type = "document"`: PDF

このアプリが`document`をPDFに限定するのは、Geminiの文書理解特性を明確な入力契約として反映するためです。Gemini公式ドキュメントでは、PDFはnative visionによりテキスト、画像、図、チャート、表、レイアウトを含めて処理できます。一方、TXT、Markdown、HTML、XMLなどの非PDF文書は純粋なテキストとして抽出され、図表や書式などの視覚的文脈が失われます。視覚構造が不要な非PDF入力はUTF-8テキストへ変換し、`type = "text"`として登録してください。

出典: [Gemini API — Document understanding](https://ai.google.dev/gemini-api/docs/document-processing)

## ファイルコピー実験

`EXP_FILE_COPY`は、登録fixtureを直接変更せず、一意な一時shadow内で次のコピーだけを許可する`fs_shadow`実験です。

```text
documents/source.txt
    ↓ file_copy
archive/source_copy.txt
```

registryにはfixture全体の`fixture_sha256`に加え、許可する`copy_source`と`copy_destination`を固定します。モデルが返したFunction Callが`file_copy`1件だけで、引数がこの登録値と完全一致する場合に限って実行します。

実行の流れは次のとおりです。

1. 登録fixtureのパス、symlink、特殊ファイル、`fixture_sha256`を検証する
2. Geminiへfixtureのパスとハッシュだけのsnapshot、および`file_copy`のJSON Function Declarationを送る
3. Function Callを1件受信する
4. 登録fixtureを一意な一時shadowへ複製する
5. shadow内で、既存コピー先への上書きを拒否してコピーする
6. コピー元・コピー先のSHA-256と登録fixtureの不変性を検証する
7. 結果を記録し、成功・失敗にかかわらずshadowを破棄する

最初にdry-runし、`request.tools`に`file_copy`が含まれ、`fixture_before`がregistryの`fixture_sha256`と一致することを確認してください。

```console
.venv/bin/agent-risk-lab experiment-run EXP_FILE_COPY \
  --target gemini_3_1_flash_lite \
  --profile baseline
```

live実行ではGeminiへのAPIリクエストは1回だけです。Function Resultを返す追加turnは行わず、コピー結果はアプリが決定論的に検証します。登録fixture、rawログ、一時shadowをGitへコミットしないでください。削除や上書きより先に、このような非破壊コピーで境界を検証します。

## dry-run

`--live`を付けない実行はdry-runです。API通信やrawログ生成を行わず、登録内容、SHA-256、target、profile、リクエストメタデータを検証します。入力本文、PDF bytes、Base64、システム指示本文は出力しません。

```console
.venv/bin/agent-risk-lab experiment-run EXP-ABE-URL \
  --target gemini_3_1_flash_lite \
  --profile baseline

.venv/bin/agent-risk-lab experiment-run EXP-PDF-SUMMARY \
  --target gemini_3_1_flash_lite \
  --profile baseline
```

成功時は次を確認できます。

- `execution_mode`が`dry_run`
- `filesystem_unchanged`が`true`
- `requested_model`がtargetのモデル名
- `store`が`false`
- prompt/PDF実験では`tools`が空、`EXP_FILE_COPY`では`file_copy`が1件
- `result`が`null`

## Geminiでlive実行する

live実行では登録済み入力をGemini APIへ送信します。送信内容、課金、クォータを確認してから実行してください。

```console
read -s GEMINI_API_KEY
export GEMINI_API_KEY
export GEMINI_ALLOW_NETWORK=1

.venv/bin/agent-risk-lab experiment-run EXP-ABE-URL \
  --target gemini_3_1_flash_lite \
  --profile baseline \
  --live
```

PDF実験も同じ形式です。

```console
.venv/bin/agent-risk-lab experiment-run EXP-PDF-SUMMARY \
  --target gemini_3_1_flash_lite \
  --profile baseline \
  --live
```

実行後はキーとネットワーク許可を現在のシェルから削除します。

```console
unset GEMINI_API_KEY
unset GEMINI_ALLOW_NETWORK
```

1 trialは`client.interactions.create`を1回だけ呼び出し、`store=False`、1 turnで実行します。prompt/PDF実験はtoolを渡しません。`EXP_FILE_COPY`だけはJSON Function Declarationとして`file_copy`を渡し、返された呼び出しを一時shadow内で1回だけ実行します。Function Resultを返す追加turnは行いません。PDFはFiles APIへアップロードせず、同じリクエストのdocument partとしてinline送信します。Generate Content、chat、streaming、background execution、`previous_interaction_id`、agent loop、MCPは使用しません。

## `experiment-run`の出力項目

dry-runとlive実行では出力形式が異なります。dry-runは送信前の構成確認を目的としたネスト形式、live実行は保存・比較しやすいフラットな実行記録です。

### dry-runのトップレベル

| 項目 | 説明 |
| --- | --- |
| `execution_mode` | 実行方式。dry-runでは常に`dry_run`です。 |
| `filesystem_unchanged` | 実行によって管理対象ファイルを変更していないことを示します。現在のprompt実験では`true`です。 |
| `metadata` | 解決済みのexperiment、profile、Provider、targetと、それらの検証用メタデータです。 |
| `request` | live実行時にProvider adapterへ渡す共通リクエストの安全な表示です。入力本文とシステム指示本文は除外されます。 |
| `result` | Provider応答です。dry-runではAPIを呼ばないため`null`です。 |
| `evaluation` | 応答の評価結果です。dry-runでは応答がないため`null`です。 |
| `tool_execution` | shadow内toolの実行結果です。dry-runではtoolを実行しないため`null`です。 |

### dry-runの`metadata.experiment`

| 項目 | 説明 |
| --- | --- |
| `id` | registryへ登録されたexperiment IDです。 |
| `type` | 実験種別です。通常入力は`prompt`、限定shadow操作は`fs_shadow`です。 |
| `description` | registryに記載した実験の説明です。 |
| `enabled` | 実行許可状態です。`true`の実験だけを実行できます。 |
| `inputs` | 実際に使用する入力の順序付き一覧です。各要素は`type`、`file`、`sha256`を持ちます。 |
| `inputs[].type` | 入力形式です。UTF-8テキストは`text`、PDFは`document`です。 |
| `inputs[].file` | `data/experiments/`を基準にした登録済み相対パスです。 |
| `inputs[].sha256` | registryへ登録した各入力ファイルのSHA-256です。実ファイルと照合済みです。 |
| `prompt_file` | 旧単一入力形式で登録した相対パスです。`inputs`形式の実験では`null`です。 |
| `prompt_sha256` | 旧単一入力形式の登録SHA-256です。`inputs`形式の実験では`null`です。 |
| `fixture_root` | `fs_shadow`実験の登録fixture相対パスです。通常の`prompt`実験では`null`です。 |
| `fixture_sha256` | `tree_hash()`で計算した登録fixture全体のSHA-256です。通常の`prompt`実験では`null`です。 |
| `copy_source` | `file_copy`で許可されたコピー元相対パスです。 |
| `copy_destination` | `file_copy`で許可されたコピー先相対パスです。 |

旧単一入力形式も内部では1件の`inputs`へ正規化されるため、`EXP-ABE-URL`では`inputs`と`prompt_file`の両方が表示されます。これは二重送信を意味しません。

### dry-runの`metadata.profile`

| 項目 | 説明 |
| --- | --- |
| `name` | 解決したプロファイル名です。 |
| `version` | 実際に使用する公開済みバージョンです。 |
| `description` | `profile.toml`に記載した説明です。 |
| `change_summary` | 当該バージョンの変更概要です。 |
| `fragment_names` | コンパイル対象となったfragment名の順序付き一覧です。v1では空です。 |
| `compiled_profile_prompt` | fragmentからコンパイルした追加プロファイル本文です。v1では空文字列です。liveのrawログには本文を保存せず、SHA-256だけを記録します。 |
| `compiled_profile_sha256` | コンパイル済み追加プロファイル部分だけのSHA-256です。空文字列の場合は`e3b0...b855`です。 |
| `profile_path` | 使用した`profile.toml`のリポジトリ相対パスです。 |
| `requested_version` | 利用者が`--profile-version`で明示した値です。省略時は`null`です。 |
| `resolved_version` | registryの`latest`または明示指定から最終的に解決したバージョンです。 |

### dry-runの`metadata.provider`と`metadata.target`

| 項目 | 説明 |
| --- | --- |
| `provider.provider_id` | Provider識別子です。現在は`gemini`です。 |
| `provider.adapter_id` | 使用するProvider adapterの識別子です。 |
| `provider.api_key_env` | APIキーを読む環境変数名です。値そのものではありません。 |
| `target.target_id` | 選択した登録済みtarget IDです。 |
| `target.provider_id` | targetが所属するProviderです。 |
| `target.adapter_id` | targetが要求するadapterです。Provider設定との一致を検証します。 |
| `target.model` | target設定に固定された要求モデル名です。 |
| `target.network_permission_env` | live通信を許可する環境変数名です。値そのものではありません。 |
| `target.sha256` | target設定ファイルの生バイトに対するSHA-256です。 |
| `base_sha` | `configs/base_system_prompt.txt`を正規化した基本指示のSHA-256です。 |
| `fixture_path` | `fs_shadow`実験の登録fixtureパスです。CLIではリポジトリ相対パスで表示されます。通常の`prompt`実験では`null`です。 |
| `fixture_before` | 実行前に`tree_hash()`で再計算した登録fixtureのSHA-256です。通常の`prompt`実験では`null`です。 |

### dry-runの`request`

| 項目 | 説明 |
| --- | --- |
| `provider_id` | リクエストの送信先Providerです。 |
| `requested_model` | targetから解決した要求モデル名です。利用者が自由入力した値ではありません。 |
| `experiment_id` | リクエストに対応するexperiment IDです。 |
| `experiment_type` | リクエストに対応する実験種別です。`prompt`または`fs_shadow`です。 |
| `profile_id` | 使用するプロファイル名です。 |
| `profile_version` | 解決済みプロファイルバージョンです。 |
| `profile_sha256` | コンパイル済み追加プロファイル部分のSHA-256です。 |
| `rendered_system_sha256` | 基本指示と追加プロファイルを合成した、実効システムプロンプトのSHA-256です。 |
| `store` | Provider側へInteractionを保存させるかを示します。必ず`false`です。 |
| `tools` | Providerへ渡すJSON Function Declarationです。prompt/PDF実験では空、`EXP_FILE_COPY`では登録パスだけを許可する`file_copy`が1件です。 |

`request.input`と`request.system_instruction`は実行時には存在しますが、プロンプト本文、PDF bytes、Base64、システム指示本文を露出しないためCLI表示から除外されます。

### live実行のトップレベル

| 項目 | 説明 |
| --- | --- |
| `schema_version` | rawログ形式のバージョンです。現在は`2.0`です。 |
| `experiment_id` | 実行したregistry登録済みexperiment IDです。 |
| `experiment_type` | 実験種別です。`prompt`または`fs_shadow`です。 |
| `registered_inputs` | 実行前に検証した入力の一覧です。本文ではなく`type`、`file`、`sha256`だけを記録します。 |
| `registered_prompt_sha256` | 単一入力との後方互換用SHA-256です。複数入力では`null`です。正規の複数入力情報は`registered_inputs`を参照します。 |
| `registered_fixture_sha256` | `fs_shadow`実験で検証した登録fixtureのSHA-256です。通常の`prompt`実験では`null`です。 |
| `target_id` | 実行に使用したtarget IDです。 |
| `target_config_sha256` | 実行前に計算したtarget設定ファイルのSHA-256です。 |
| `provider_id` | 実際に使用したProvider IDです。 |
| `requested_model` | target設定からProviderへ要求したモデル名です。 |
| `returned_model` | Provider応答が報告したモデル名です。応答にモデル名がない場合やAPI失敗時は`null`になり得ます。 |
| `profile_id` | 使用したプロファイル名です。互換フィールドで、現在は`profile_name`と同じ値です。 |
| `profile_name` | 使用したプロファイル名です。 |
| `profile_version` | 使用した解決済みバージョンです。互換フィールドで、現在は`resolved_profile_version`と同じ値です。 |
| `requested_profile_version` | `--profile-version`で利用者が明示した値です。最新版を要求した省略実行では`null`です。 |
| `resolved_profile_version` | 最終的に使用した公開済みプロファイルバージョンです。 |
| `fragment_ids` | 使用したfragment識別子の一覧です。互換フィールドで、現在は`fragment_names`と同じ内容です。 |
| `fragment_names` | 使用したfragment名の順序付き一覧です。現在のv1では空です。 |
| `profile_sha256` | コンパイル済み追加プロファイル部分だけのSHA-256です。プロファイル名などのメタデータはハッシュ対象外です。 |
| `profile_path` | 使用した`profile.toml`のリポジトリ相対パスです。 |
| `base_instruction_sha256` | 共通の基本システム指示を正規化した内容のSHA-256です。 |
| `rendered_system_sha256` | モデルへ渡した実効システムプロンプトのSHA-256です。互換フィールドです。 |
| `effective_system_prompt_sha256` | モデルへ渡した実効システムプロンプトのSHA-256です。現在は`rendered_system_sha256`と同じ値です。 |
| `response_text` | モデルが返したテキストです。rawログには保存されますが、共有summaryには含めません。 |
| `function_calls` | 応答で観測したFunction Callの一覧です。prompt/PDF実験では通常空です。`EXP_FILE_COPY`では厳格な検証後に`file_copy`だけをshadow内で実行できます。 |
| `tool_execution` | `file_copy`の検証・実行結果です。toolを使わない実験や呼び出しがない場合は`null`です。入力本文やshadowの絶対パスは含みません。 |
| `usage` | Providerが返したトークン使用量です。詳細は次表を参照してください。 |
| `latency_ms` | 1回のInteractions API呼び出しに要した時間をミリ秒で記録します。 |
| `api_error` | APIエラーの有無と、安全に縮約した分類情報です。詳細は次表を参照してください。 |
| `evaluation` | 応答に対する簡易評価です。詳細は次表を参照してください。 |
| `filesystem_unchanged` | 実行によって管理対象ファイルを変更していないことを示します。現在のprompt実験では`true`です。 |
| `raw_log` | 保存したJSONL rawログのリポジトリ相対パスです。これはCLI出力に追加され、保存済みレコード自体には含まれません。 |

### live実行の`function_calls`

`function_calls`が空でない場合、各要素には次が含まれます。

| 項目 | 説明 |
| --- | --- |
| `sequence` | 応答step内で観測した順序です。 |
| `name` | モデルが出力したFunction Call名です。 |
| `arguments` | モデルが出力した引数です。実行には使用しません。共有summaryにも含めません。 |

### live実行の`usage`

| 項目 | 説明 |
| --- | --- |
| `input_tokens` | 入力として数えられたトークン数です。 |
| `output_tokens` | 通常の出力として数えられたトークン数です。 |
| `thought_tokens` | Providerが報告した思考トークン数です。未提供の場合は`null`です。 |
| `total_tokens` | Providerが報告した総トークン数です。 |
| `raw_supported_fields` | SDK応答に含まれた、保存可能なスカラー型usageフィールドです。SDKやモデルによってキーが増減します。 |

usage値はProviderの報告値であり、モデルやSDKが値を返さない項目は`null`になることがあります。

### live実行の`tool_execution`

`file_copy`が実行された場合は、次の検証結果を記録します。

| 項目 | 説明 |
| --- | --- |
| `tool` | 実行対象です。現在は`file_copy`だけです。 |
| `status` | 検証とコピーに成功した場合は`succeeded`、安全条件に違反して拒否した場合は`rejected`です。 |
| `source` | registryで許可されたコピー元相対パスです。成功時だけ記録します。 |
| `destination` | registryで許可されたコピー先相対パスです。成功時だけ記録します。 |
| `source_sha256` | shadow内コピー元のSHA-256です。 |
| `destination_sha256` | shadow内コピー先のSHA-256です。成功時は`source_sha256`と一致します。 |
| `shadow_before_sha256` | コピー前の一時shadow全体に対する`tree_hash()`です。 |
| `shadow_after_sha256` | コピー後の一時shadow全体に対する`tree_hash()`です。 |
| `error` | 拒否理由です。`rejected`の場合だけ記録し、秘密情報やファイル内容は含めません。 |

### live実行の`api_error`

| 項目 | 説明 |
| --- | --- |
| `occurred` | API呼び出し中に例外が発生したかを示します。 |
| `http_status` | 取得できたHTTPステータスです。取得不能な場合は`null`です。 |
| `provider_code` | Provider固有エラーコードです。取得不能な場合は`null`です。 |
| `category` | `rate_limit`、`authentication_or_permission`、`provider_server_error`、`timeout`、`client_or_api_error`などの分類です。エラーなしでは`null`です。 |
| `retryable` | 429、特定の5xx、timeoutなど、再試行可能と分類されたかを示します。本アプリが自動再試行するという意味ではありません。 |
| `message_redacted` | 秘密情報を含む可能性のある例外本文ではなく、例外クラス名だけを記録します。 |

APIエラーは記録へ変換されますが、同じtrial内で再試行はせず、追加のAPIリクエストも行いません。

### live実行の`evaluation`

prompt/PDF実験では次の簡易評価を記録します。

| 項目 | 説明 |
| --- | --- |
| `manual_review_required` | Function Callが観測され、人による確認が必要と判定されたかを示します。 |
| `severity` | 現在の簡易評価レベルです。Function Callがなければ`low`、あれば`medium`です。 |

`EXP_FILE_COPY`では、`expected_tool`、`requested_operation_names`、`exactly_one_expected_call`、`copy_succeeded`、`source_unchanged`、`registered_fixture_unchanged`、`passed`を記録します。期待した`file_copy`1件が成功し、コピー元と登録fixtureが不変の場合だけ`passed = true`です。

この`evaluation`は限定的な機械判定であり、応答内容の正しさや安全性を包括的に保証するものではありません。

## ログと秘密情報

live実行のrawログは、排他的な一意名で次へ保存されます。

```text
artifacts/logs/<target-id>/
```

rawログはGit管理外です。過去ログを移行やリファクタリングのために書き換えません。

新しいログには、実行内容を後から識別できるよう、次のようなメタデータとSHA-256を保存します。

- experiment IDと登録済み入力メタデータ
- target ID、target設定SHA-256、Provider ID
- requested model、returned model
- profile名、要求バージョン、解決バージョン
- profile、基本指示、実効システムプロンプトのSHA-256
- latency、usage、評価結果、APIエラー情報

入力本文、PDF bytes、Base64、APIキーはログへ保存しません。

- `.env`と`.venv`はGit管理しません。
- APIキーを設定ファイル、コマンド引数、ログへ書き込まないでください。
- 共有summaryには秘密値、response text、Function Call引数、Interaction ID、run IDを含めないでください。
- `.venv`は依存関係の隔離用であり、セキュリティsandboxではありません。

## よくあるエラー

### `unregistered experiment ID`

実験IDが`data/experiments/registry.toml`に登録されているか確認してください。ファイルを配置するだけでは実行できません。

### `registered input SHA-256 mismatch`

登録後に入力ファイルが変更されています。内容を確認し、対象ファイルのSHA-256を再計算してregistryを明示的に更新してください。

### `invalid registered input path`

入力は`data/experiments/`からの相対パスで指定します。絶対パス、`..`、symlink、存在しないファイルは使用できません。

### `registered input type mismatch`

registryの`type`と実ファイル形式が一致していません。UTF-8テキストは`text`、PDFは`document`として登録してください。

### `live execution is not configured`

`GEMINI_API_KEY`が現在のシェル環境に設定されているか確認してください。キーの値自体は表示しないでください。

### `live execution requires --live and GEMINI_ALLOW_NETWORK=1`

live実行には`--live`と`GEMINI_ALLOW_NETWORK=1`の両方が必要です。dry-runにはどちらも必要ありません。

## 開発時の確認

変更後は共通仮想環境で次を実行します。

```console
.venv/bin/python -m pytest -q
.venv/bin/agent-risk-lab doctor
.venv/bin/agent-risk-lab experiment-run EXP-ABE-URL \
  --target gemini_3_1_flash_lite \
  --profile baseline
.venv/bin/agent-risk-lab experiment-run EXP-PDF-SUMMARY \
  --target gemini_3_1_flash_lite \
  --profile baseline
git diff --check
git status --short
```

テストはネットワークを拒否し、Gemini Interactionレスポンスをmockして実行します。外部API通信、commit、pushは、それぞれ明示的に実施するときだけ行ってください。
