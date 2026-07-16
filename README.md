# Agent Risk Lab

承認済みプロンプトを同じ実験契約で評価する共通基盤です。Provider共通設定は `configs/providers/`、Providerとモデルの組合せは `configs/targets/` で管理します。現在のtargetは `gemini_3_1_flash_lite` のみです。

## 安全モデル

実験は `data/experiments/<experiment-id>/` に保存し、`data/experiments/registry.toml` へ登録された実験だけを実行できます。レジストリ未登録のファイルや任意パスは実行できません。

registryの `prompt_sha256` は実行前に実ファイルから再計算され、登録後の改変を検出します。実験内容を修正した場合は、利用者が内容を確認した上で `prompt_sha256` も明示的に更新してください。実在する個人情報、credentials、APIキー、認証情報を置かないでください。

## 実行

このリポジトリはclone先の絶対パスに依存しません。Python 3.12以上で、リポジトリルートに共通仮想環境を1つ作成します。

```console
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Providerごとに別の仮想環境は作成しません。activateの有無に関わらず同じ実行環境を使えるよう、以下の例はリポジトリルートからの相対パスを使います。

```console
.venv/bin/agent-risk-lab list-profiles
.venv/bin/agent-risk-lab show-profile hardened
.venv/bin/agent-risk-lab list-experiments
.venv/bin/agent-risk-lab show-experiment EXP-ABE-URL
```

dry-run（既定、API通信なし）:

```console
.venv/bin/agent-risk-lab experiment-run EXP-ABE-URL \
  --target gemini_3_1_flash_lite \
  --profile baseline

.venv/bin/agent-risk-lab experiment-run EXP-ABE-URL \
  --target gemini_3_1_flash_lite \
  --profile hardened \
  --profile-version 1
```

### 共通プロファイルのバージョン管理

プロファイルは `configs/profiles/<name>/v<version>/profile.toml` に保存し、`configs/profiles/registry.toml` で公開済みバージョンを管理します。通常実行は `latest` を使用し、過去バージョンは `--profile-version` で明示できます。公開済みバージョンは変更せず、修正時は既存バージョンを上書きせず新しいバージョンを作成してください。

初期の `baseline` v1と `hardened` v1はどちらもfragmentを追加せず、意図的に同じ実効システムプロンプトを生成します。現時点で `hardened` v2以降は存在しません。`profile_sha256` はメタデータではなく、コンパイルされた追加プロファイル部分のSHA-256です。

既定はdry-runでAPI通信もadapter生成も行いません。実通信は次の両方が必要です。

```console
GEMINI_ALLOW_NETWORK=1 .venv/bin/agent-risk-lab experiment-run EXP-ABE-URL --target gemini_3_1_flash_lite --profile hardened --live
```

`--live` では登録済み入力がGemini APIへ送られます。1 trialは `client.interactions.create` 1回、`store=False`、1 turnです。Function Callは観測・評価するだけで実行せず、Function Result、Files API、streaming、background、automatic function calling、検索、MCPは使いません。`gemini-injection-lab` はCLI互換aliasですが、旧sampleコマンド/IDは利用できません。

## 秘密情報と成果物

`.env` はGit管理せず、設定ファイルにAPIキーを保存しません。schema 2.0のrawログは `artifacts/logs/<target_id>/` に排他的な一意名で保存され、Git管理しません。共有summaryにはresponseやFunction Call引数等を含めないでください。`.venv` は依存隔離であり、セキュリティsandboxではありません。

オフライン確認は `.venv/bin/python -m pytest -q`、`.venv/bin/agent-risk-lab doctor` を使用します。
