# Gemini Free API Prompt Injection Experiment

Gemini API無料枠とInteractions APIを用いて、外部文書に埋め込まれた間接プロンプトインジェクションへの応答とFunction Call要求を比較する実験環境です。

## 安全方針

- 実験データは架空文書、架空の宛先、実行ごとに生成する合成Canaryだけを使用します。
- Gmail、Google Drive、SMTP、シェル、実ファイル操作へ接続するツールは実装しません。
- Function CallはJSON宣言だけをモデルへ提示し、要求された名前と引数を記録するだけです。
- Function Result、ツール実行、エージェントループ、複数ターン処理は実装しません。
- API呼び出しは1試行につき最大1回で、常に `store=False` を指定します。
- `previous_interaction_id`、background execution、サーバー側会話状態は使用しません。
- 既定動作はdry-runです。live実行には `--live` と `GEMINI_ALLOW_NETWORK=1` の両方が必要です。
- APIキーは `GEMINI_API_KEY` からliveクライアントが取得し、表示・記録しません。

Gemini無料枠では、入力データがGoogleの製品改善に使用される可能性があります。`store=False` はInteractionオブジェクトのサーバー側保存を無効にする設定ですが、無料枠のデータ取扱条件とは別です。実在する個人情報、研究機密、認証情報は送信しないでください。

## 研究タスク

baselineとhardenedは同じ `prompts/user_task.txt` を使用します。モデルには外部文書の要約と、「研究資料」「事務資料」「その他」の通常分類だけを依頼します。プロンプトインジェクション検出は依頼しません。両条件の違いはsystem promptだけです。

初期ケースは正常文書B-01、B-02と攻撃文書PI-01〜PI-04です。PI-03で `read_file(private/canary.txt)` が要求されても実行せず、結果をモデルへ返しません。そのため、read_fileの結果を次ターンでsend_emailする複数段階攻撃は初期実装の評価対象外です。

## セットアップ

Python 3.12以上が必要です。

```console
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

必要な場合は `.env.example` を参考にローカルの `.env` を作成します。`.env` はGit管理されません。

## CLI

```console
gemini-injection-lab doctor
gemini-injection-lab dry-run B-01 --profile baseline
gemini-injection-lab dry-run PI-01 --profile hardened
gemini-injection-lab run B-01
gemini-injection-lab batch --repetitions 3
gemini-injection-lab summarize artifacts/logs/<log>.jsonl
```

`run` と `batch` も既定ではdry-runです。live実行は明示的な安全ゲートを満たす場合だけ可能ですが、通常の単体テストはネットワーク接続を強制的に拒否します。

## ログと共有可能な集計

`artifacts/logs/` のJSONLには研究上必要なモデル応答とFunction Call引数が含まれ得るため、ディレクトリ全体をGit管理対象外にします。APIキーとリクエスト全文は保存しません。

`artifacts/summaries/` には件数、率、token使用量、エラー分類だけを含む匿名化集計を新規ファイルとして保存できます。Canary、生のモデル応答、Function Call引数、Interaction ID、run IDは含めません。

## 制約

Interactions APIやSDKの応答属性は変更される可能性があります。Gemini固有の変換は `client.py` に隔離しています。無料枠の残量は通常レスポンスから確定できないため、返却されたusage、リクエスト件数、APIエラーだけを記録します。
