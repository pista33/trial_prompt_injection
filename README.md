# Agent Risk Lab

登録済みプロンプトを、Providerとモデルの組合せを明示して評価する実験基盤です。Provider共通設定は `configs/providers/`、Providerとモデルの組合せは `configs/targets/` で管理します。現在利用できるtargetは `gemini_3_1_flash_lite` です。

## 1. 必要環境

- Git
- Python 3.12以上
- live実行を行う場合のみGemini APIキー

以下のコマンドはmacOS/Linuxのシェルを想定しています。Windowsでは `.venv/bin/` を `.venv\Scripts\` に読み替えてください。

## 2. cloneとセットアップ

```console
git clone <repository-url>
cd trial_prompt_injection
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install '.[dev]'
```

仮想環境はリポジトリルートの `.venv` 1つだけを使います。

セットアップを確認します。

```console
.venv/bin/python -c "import sys; print(sys.executable); print(sys.prefix)"
.venv/bin/agent-risk-lab doctor
.venv/bin/python -m pytest -q
```

`doctor` の出力が `"ok": true` で、pytestが成功すれば準備完了です。activate済みでも、以下の例はclone先に依存しない相対パスを使います。

## 3. 既存実験をdry-runする

登録済みの実験とプロファイルを確認します。

```console
.venv/bin/agent-risk-lab list-experiments
.venv/bin/agent-risk-lab show-experiment EXP-ABE-URL
.venv/bin/agent-risk-lab list-profiles
.venv/bin/agent-risk-lab show-profile baseline
```

`EXP-ABE-URL` をdry-runします。`--live` を付けない限りAPI通信は行われません。

```console
.venv/bin/agent-risk-lab experiment-run EXP-ABE-URL \
  --target gemini_3_1_flash_lite \
  --profile baseline
```

成功時は出力の次の項目を確認できます。

- `execution_mode` が `dry_run`
- `experiment.id` が `EXP-ABE-URL`
- `prompt_file` が `EXP-ABE-URL/prompt.txt`
- `requested_model` が `gemini-3.1-flash-lite`
- `store` が `false`
- `result` が `null`

## 4. 新しい実験を作成する

例として `EXP-MY-001` を作成します。実験IDごとにディレクトリを作り、確認済みのプロンプトだけを配置してください。

```console
mkdir -p data/experiments/EXP-MY-001
```

`data/experiments/EXP-MY-001/prompt.txt` をUTF-8で作成し、実験したいプロンプトを記述します。実在する秘密情報、APIキー、credentials、不要な個人情報は保存しないでください。

ファイルのSHA-256をバイト単位で算出します。

```console
.venv/bin/python -c "import hashlib, pathlib; p=pathlib.Path('data/experiments/EXP-MY-001/prompt.txt'); print(hashlib.sha256(p.read_bytes()).hexdigest())"
```

出力された64文字のハッシュを使い、`data/experiments/registry.toml` の末尾に次を追記します。

```toml
[[experiments]]
id = "EXP-MY-001"
type = "prompt"
description = "Describe this experiment."
prompt_file = "EXP-MY-001/prompt.txt"
prompt_sha256 = "<calculated-sha256>"
enabled = true
```

登録を確認します。

```console
.venv/bin/agent-risk-lab list-experiments
.venv/bin/agent-risk-lab show-experiment EXP-MY-001
```

新しい実験をdry-runします。

```console
.venv/bin/agent-risk-lab experiment-run EXP-MY-001 \
  --target gemini_3_1_flash_lite \
  --profile baseline
```

registryに未登録のファイルは実行できません。また、実験ファイルを修正すると次回実行時にSHA-256不一致で停止します。内容を再確認し、同じコマンドでハッシュを再計算して `prompt_sha256` を明示的に更新してください。

## 5. プロファイルを選択する

プロファイルは `configs/profiles/<name>/v<version>/profile.toml` に保存し、`configs/profiles/registry.toml` で公開済みバージョンを管理します。バージョン省略時はregistryの `latest` が使用されます。

```console
.venv/bin/agent-risk-lab experiment-run EXP-ABE-URL \
  --target gemini_3_1_flash_lite \
  --profile hardened

.venv/bin/agent-risk-lab experiment-run EXP-ABE-URL \
  --target gemini_3_1_flash_lite \
  --profile hardened \
  --profile-version 1
```

公開済みバージョンは上書きせず、修正時は新しいバージョンを作成してください。現在の `baseline` v1と `hardened` v1はどちらもfragmentを追加せず、意図的に同じ実効システムプロンプトを生成します。`profile_sha256` はメタデータではなく、コンパイルされた追加プロファイル部分のSHA-256です。

## 6. Geminiでlive実行する（任意）

live実行では登録済み入力がGemini APIへ送信されます。課金、クォータ、送信内容を確認してから実行してください。

APIキーを設定し、ネットワーク許可ゲートを明示的に有効化します。

```console
read -s GEMINI_API_KEY
export GEMINI_API_KEY
export GEMINI_ALLOW_NETWORK=1
```

```console
.venv/bin/agent-risk-lab experiment-run EXP-ABE-URL \
  --target gemini_3_1_flash_lite \
  --profile baseline \
  --live
```

実行後はキーをシェル環境から削除します。

```console
unset GEMINI_API_KEY
unset GEMINI_ALLOW_NETWORK
```

1 trialは `client.interactions.create` を1回だけ呼び出し、`store=False`、1 turnで実行します。Function Callは観測・評価するだけで実行しません。Function Result、Files API、streaming、background execution、automatic function calling、MCPは使いません。

## 7. ログと秘密情報

- `.env` と `.venv` はGit管理しません。
- APIキーを設定ファイル、コマンド引数、ログへ書き込まないでください。
- live実行のrawログは `artifacts/logs/<target_id>/` に排他的な一意名で保存され、Git管理されません。
- 共有summaryにはCanary値、response text、Function Call引数、Interaction ID、run IDを含めないでください。
- `.venv` は依存関係の隔離用であり、セキュリティsandboxではありません。

## 8. よくあるエラー

### `unregistered experiment ID`

実験IDが `data/experiments/registry.toml` に登録されているか確認してください。ファイルを置くだけでは実行できません。

### `registered prompt SHA-256 mismatch`

登録後に `prompt.txt` が変更されています。内容を確認し、SHA-256を再計算してregistryを明示的に更新してください。

### `invalid registered prompt path`

`prompt_file` は `data/experiments/` からの相対パスで指定します。絶対パス、`..`、symlink、存在しないファイルは使用できません。

### `live execution is not configured`

`GEMINI_API_KEY` が現在のシェル環境に設定されているか確認してください。キーの値自体は表示しないでください。

### `live execution requires --live and GEMINI_ALLOW_NETWORK=1`

live実行には `--live` と `GEMINI_ALLOW_NETWORK=1` の両方が必要です。dry-runにはどちらも必要ありません。
