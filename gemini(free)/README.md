# Gemini Free API Prompt Injection Experiment

Gemini APIの無料枠を用いて，間接プロンプトインジェクションへの応答を評価する実験環境．

## 安全方針

- 実在する個人情報や機密情報を使用しない
- 実メールを送信しない
- 実ファイルの削除，移動，上書きを行わない
- 危険なFunction Callは要求内容だけを記録する
- APIキーをGitへ登録しない
- 実験用のCanary文字列のみを使用する
