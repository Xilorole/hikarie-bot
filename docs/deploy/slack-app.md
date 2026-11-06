# 本番の Slack アプリの設定

dev アプリは `slack run` のときに `manifest.json` から設定されるが、本番の Slack アプリは手で設定する。
機能を足したときに本番のアプリで一度だけ必要になる設定を、ここにまとめる。どこで動かすか（Rancher、docker compose）には関係しない。

設定より先にデプロイしても、その機能が Slack に出ないだけで、ほかの機能は変わらない。

## 出社登録ショートカット

利用者は Slack の **グローバルショートカット「出社した」**（検索欄の左の「+」や `/` メニュー）から、当日の投稿を探さずに出社登録できる。
アプリ設定の **Interactivity & Shortcuts → Shortcuts** で次を追加する。

| 項目 | 値 |
|---|---|
| 種類 | Global |
| Name | 出社した |
| Short Description | 今日の出社を登録する |
| Callback ID | `arrive` |

追加のスコープは要らない（`commands` と `channels:history` は付与済み）。登録は当日の投稿のスレッドに記録され、結果はモーダルで返る。

## App Home

アプリの「ホーム」タブに、マイページ・図鑑・ランキング・あそびかたを出す（開くたびに計算し直す。保存するものはない）。
アプリ設定で次を有効にする。

| 画面 | 設定 |
|---|---|
| **App Home → Show Tabs** | **Home Tab** をオン |
| **Event Subscriptions** | **Enable Events** をオンにし、**Subscribe to bot events** に `app_home_opened` を追加 |

Socket Mode なので Request URL は要らない。設定を保存したら、アプリの再インストールを求められれば従う。

### 毎朝の投稿の「マイページを開く」

毎朝の投稿のボタンからホームのマイページを開くリンクは、ボットが起動時に Slack から取得した値で作る。
`BOT_ID` / `SLACK_WORKSPACE_ID` / `SLACK_APP_ID` は環境変数に入れなくてよい（入れた値は優先される）。

- `auth.test` でボットとワークスペースの ID、`bots.info` でアプリの ID を取る。
- `bots.info` には Bot Token Scope の `users:read` が要る（**OAuth & Permissions → Scopes** に追加して再インストール）。
  足りなければ警告を出してボタンなしで起動する。

ボタンは `slack://app?team=…&id=…&tab=home` でホームタブを開き、押した人のホームをマイページにする。
ワークスペースとアプリの ID のどちらかが取れなければボタンは出ない。前の「ステータス」ボタンは、押すとマイページに移ったことを伝える。
