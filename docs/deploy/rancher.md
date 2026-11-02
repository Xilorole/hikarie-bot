# Rancher（2.9.3）へのデプロイ

`rebuild` の構成（PVC 上の SQLite に出社イベントを保存し、起動時に Slack を読むのは DB が空のときだけ）を
Rancher で動かす手順。マニフェストは [`deploy/rancher/`](../../deploy/rancher/) にある。

## 全体像

| リソース | 役割 |
|---|---|
| PersistentVolumeClaim `hikarie-bot-data` | SQLite（`/opt/.db/data.db`）を置く EBS ボリューム（`ebs-sc`、1Gi、ReadWriteOnce） |
| Secret `hikarie-bot` | Slack のトークン・チャンネル・bot ID など（`.env.template` と同じキー） |
| Deployment `hikarie-bot` | bot 本体。1 台のみ、更新は `Recreate`、UID/GID 10001 で動かす |

- **Pod は 1 台だけ**: 2 台にすると Slack のイベントが分散し、1 つの SQLite を取り合う。
- **更新方式は `Recreate`**: EBS は 1 ノードにしか付かないため、ローリング更新だと新しい Pod が起動できない。
  そのため更新中は数十秒 bot が止まる。
- **`fsGroup: 10001`**: コンテナは UID 10001 で動くので、ボリュームを書き込めるようにする。
- **`DATABASE_URL`** は `sqlite:////opt/.db/data.db`（PVC 上のファイル）。`sqlite:///:memory:` のままだと起動時にエラーで止まる（再起動のたびに全データが消えるため）。
- EBS はアベイラビリティゾーンに紐づくため、Pod はそのゾーンのノードにだけ配置される。

## 事前準備

1. `rebuild` が main にマージされ、Release ワークフローがイメージを公開していること。
   デプロイするコミットのイメージタグ（`sha-` ＋ コミットの先頭 7 文字）を確認する。
2. 既存のワークロードが ghcr.io から pull するのに使っている **Registry Secret の名前**を確認する
   （Storage → Secrets で種類が Registry のもの）。`deployment.yaml` の `imagePullSecrets` をその名前に合わせる（例では `ghcr`）。
3. 今のワークロードの環境変数（チャンネル・bot ID・トークン）を控えておく。

## 手順

### 1. PVC を作る

Storage → PersistentVolumeClaims → Create:

- Name: `hikarie-bot-data`
- Storage Class: `ebs-sc`
- Request Storage: `1` GiB、Access Mode: Single-Node Read/Write

または右上の「Import YAML」で [`pvc.yaml`](../../deploy/rancher/pvc.yaml) を貼り付ける。
StorageClass が WaitForFirstConsumer の場合、Pod が付くまで `Pending` のままなのは正常。

### 2. Secret を作る

Storage → Secrets → Create → Opaque:

- Name: `hikarie-bot`
- キー: `OUTPUT_CHANNEL` `LOG_CHANNEL` `BOT_ID` `ADMIN` `SLACK_BOT_TOKEN` `SLACK_APP_TOKEN`

[`secret.example.yaml`](../../deploy/rancher/secret.example.yaml) を手元でコピーして値を入れ、Import YAML で取り込んでもよい
（値を入れたファイルはコミットしない）。既存ワークロードの環境変数で渡し続ける場合は、このステップは省略できる。

### 3. Deployment を更新する

既存のワークロード（Workloads → Deployments）の ⋮ → Edit Config:

- **Image**: `ghcr.io/xilorole/hikarie-bot:sha-XXXXXXX`（デプロイするタグ）
- **Command / Args**: 空のまま（イメージの既定 `python -m hikarie_bot start`）。以前の `--skip-db-create` は削除済みのオプションなので付けない
- **Environment Variables**:
  - Secret `hikarie-bot` を参照（Type: Secret, 全キー）、または既存の変数を残す
  - `DATABASE_URL` = `sqlite:////opt/.db/data.db`（`URL` や `sqlite:///:memory:` の設定は削除）
- **Storage**: Add Volume → Persistent Volume Claim → `hikarie-bot-data`、Mount Point `/opt/.db`
- **Scaling and Upgrade Policy**: Recreate、Replicas 1
- **Pod → Security Context**: Filesystem Group `10001`（Run as User / Group も `10001`）

UI に項目が見当たらない場合は ⋮ → Edit YAML で [`deployment.yaml`](../../deploy/rancher/deployment.yaml) の該当部分を反映する。
新規に作る場合は 3 つのマニフェストをそのまま Import YAML してよい。

### 4. 初回起動を確認する

PVC が空の初回だけ、チャンネル全体（メッセージ約 7,500 件・bot のスレッド約 500 件）を読む。
レート制限の待ちを含めて **10 分前後**かかり、その間 bot は Slack に接続していない（ボタンは反応しない）。
**18 時以降か休日**に行うのがよい。

ログチャンネルに、手順ごとに次のメッセージが届く（個人を特定できる情報は含まない）:

1. `starting application (rev 6709a7d)` — `rev` はイメージのビルド元コミット。Rancher で指定したタグ `sha-6709a7d` と一致すれば最新が動いている
2. `*database*: schema 0000 …` — スキーマとバッジ定義の同期結果
3. `first start: reading the whole channel …` — 初回だけ。この後 10 分前後かかる
4. `*slack sync*: whole channel · … messages · … threads · … new events` — DB が空でなければ読まず `skipped (N events stored)`
5. `*scores*: … events → … arrivals · … users · … badges earned`
6. `:white_check_mark: application started (rev …) in …s`

途中で失敗した場合は `:warning: startup failed at <手順>` が届き、詳細は Pod のログに残る。
2 回目以降は Slack を読まないので数秒で終わる。

### 5. 動作確認

- 出社ボタンを押し、スレッドにポイントのメッセージが付くこと
- 必要なら件数を確認する（読み取りのみ）:

```bash
kubectl exec deploy/hikarie-bot -- /opt/.venv/bin/python -c "import sqlite3; c = sqlite3.connect('file:/opt/.db/data.db?mode=ro', uri=True); print(c.execute('select count(*) from arrival_event').fetchone(), c.execute('select version_num from alembic_version').fetchone())"
```

### 再起動

管理者（環境変数 `ADMIN` のユーザー）は、Slack の **メッセージショートカット「reboot」**（bot がいるチャンネルのメッセージの「…」→ ショートカット）で再起動できる。
bot は `rebooting...` と返してプロセスを終了し、Kubernetes がコンテナを起動し直す（PVC のデータを使い、Slack は読まないので数秒）。
同じイメージで起動し直すだけなので、新しいバージョンにするにはイメージのタグを変える。

## ロールバック

戻し先のイメージによって手順が違う。

- **PVC を使う前のイメージ**（`DATABASE_URL` を読まない）: Image のタグを戻すだけでよい。メモリ上の DB で動き、起動時に全履歴を読み直す。PVC のデータには触れない。
- **PVC を使うが、スキーマが新しいイメージより古いイメージ**（例: リビジョン 0002 を含まないイメージ）: タグを戻すだけだと、起動時のマイグレーションが
  `Can't locate revision identified by '0002'` で止まる（データは変わらないので、タグを元に戻せば復旧する）。
  先に、**動いている新しいイメージで** DB を戻し先のリビジョン（0002 を含まない最後のイメージなら `0001`、0001 より前なら `0000`）まで downgrade してから、タグを変える。
  イメージには `alembic.ini` が無いので、Python から実行する:

  ```bash
  kubectl exec deploy/hikarie-bot -- /opt/.venv/bin/python -c "from alembic import command; from alembic.config import Config; from hikarie_bot.migrations import SCRIPT_LOCATION; config = Config(); config.set_main_option('script_location', str(SCRIPT_LOCATION)); command.downgrade(config, '0001')"
  ```

  0002 の downgrade は `sync_state` を空で作り直す（位置が無いので、戻し先のイメージは起動時にチャンネル全体を一度読む。約 13 分）。
  0001 の downgrade は、削除した派生テーブルとバッジ定義のテーブルを空で作り直す（`arrival_event` はそのまま）。
  戻し先のイメージは起動時にバッジ定義を入れ直し、スコアを計算し直して埋める。
  downgrade の後は再起動（reboot ショートカットを含む）をせずに、すぐタグを変える。新しいイメージのまま再起動すると、また最新に上がる。
- 新しいイメージへ戻すときは、タグを変えるだけでよい（起動時に最新のリビジョンまで上がる）。

## バックアップと復旧

- データは Slack から作り直せる。PVC を失ったら、空の PVC で起動すれば初回と同じく全件を読み直す。
- **古いバックアップを戻したとき**は、バックアップ以降の出社が DB に無く、起動時の同期は DB が空でないので走らない。復元後に手動で全件を読む（約 13 分、冪等。重複は入らない）:

  ```bash
  kubectl exec deploy/hikarie-bot -- /opt/.venv/bin/python -m hikarie_bot sync
  ```
- 手元にコピーを取る場合（実データなので扱いに注意）。ルートファイルシステムは読み取り専用なので、PVC 上に書いてから取り出し、最後に消す:

```bash
POD=$(kubectl get pod -l app=hikarie-bot -o name | head -1)
kubectl exec "$POD" -- /opt/.venv/bin/python -c "import sqlite3; sqlite3.connect('/opt/.db/data.db').backup(sqlite3.connect('/opt/.db/backup.db'))"
kubectl cp "${POD#pod/}:/opt/.db/backup.db" ./hikarie-backup.db
kubectl exec "$POD" -- rm /opt/.db/backup.db
```
- クラスタに VolumeSnapshotClass があれば、EBS スナップショットでも取れる。

## 後片付け

`rebuild` が main に入ると Release ワークフローは `hikarie-bot-initial-data` を公開しなくなる。
その後、GitHub の Packages → `hikarie-bot-initial-data` → Package settings → Delete this package で削除する（public で中身は空の manifest のみ）。
