# 実行手順

## 実行環境と範囲

Google ColabのLinux GPUランタイム（記録時はA100 80GB）を使用します。MacのローカルPythonではROS用バイナリや`/content`を利用できません。Ubuntu 22.04/24.04の分岐はセットアップに含まれますが、全OS・全GPUでの動作確認を意味しません。

`it_desk/setup_ai.py`は記録時のPyTorch 2.11.0 CUDA 12.8、torchvision 0.26.0、LeRobot 0.6.1、transformers 5.5.4を指定します。ベースモデルはrevision固定です。依存パッケージやAPT配布物の完全なロックではありません。

本書では、環境構築、教師データ収集、学習、搬送評価の順に実行する手順を説明します。各段階の完了を確認してから次へ進んでください。

学習済みモデルと教師データは同梱していません。再実行する場合は、以下の手順に従って教師データの収集と学習を行ってください。

## コマンドで実行する場合

以下はリポジトリのルートで実行します。セットアップはAPTを変更するため、Colabなど専用の使い捨て環境を使用してください。

```bash
bash it_desk/setup_sim.sh
python3 it_desk/setup_ai.py --venv /content/pai_kojikoji_s/venv_cu128_v4
bash scripts/ros_run.sh prepare_robot.py
bash scripts/ros_run.sh verify_static.py
bash scripts/ros_run.sh test_control_interface.py
```

### 教師データと初回学習

```bash
bash scripts/ros_run.sh collect.py --out /content/pai_run/train --count 24 --seed 100 --duration 150
bash scripts/ros_run.sh collect.py --out /content/pai_run/validation --count 6 --seed 300 --duration 150
/content/pai_kojikoji_s/venv_cu128_v4/bin/python it_desk/train.py --train /content/pai_run/train --validation /content/pai_run/validation --out /content/pai_run/checkpoint --steps 500
```

モデル・トークナイザの利用条件への同意が必要な場合はHugging Face側で行います。必要なモデルに限定した読み取りトークンを使用し、ノートブックやGitへ書き込まないでください。公開ノートブックはColab Secretsまたは非表示入力で取得し、学習・評価の子プロセスだけに渡します。CLIでは対象プロセスにのみ`HF_TOKEN`を渡し、コマンド履歴にトークンを直接記載しないでください。

収集は失敗試行も保持します。学習に使われるのは成功データだけです。記録時は学習用24試行のうち23試行、検証用6試行を使用しました。再実行で同じ成功数・同一重みになることは保証しません。

### 追加学習

```bash
/content/pai_kojikoji_s/venv_cu128_v4/bin/python it_desk/train_refine.py --train /content/pai_run/train --validation /content/pai_run/validation --init /content/pai_run/checkpoint --out /content/pai_run/checkpoint_refined --steps 1000
```

元の重みを引き継ぎ、AdamWは新規です。`partial.safetensors`は途中保存であり、完了モデルではありません。`training_result.json`の`status=trained`と`expert.safetensors`が揃ってから評価します。既存の出力先を削除してやり直すのではなく、新しいフォルダを指定してください。

### 学習済みモデルで搬送評価

```bash
python3 scripts/evaluate.py --python /content/pai_kojikoji_s/venv_cu128_v4/bin/python --checkpoint /content/pai_run/checkpoint_refined --out /content/pai_run/evaluation_new
```

このコマンドは、学習済みモデルを読み込み、推論サーバーの起動と2試行の搬送評価を実行します。再学習は行いません。

搬送制御本体はGazeboで2試行の成功を確認したコードです。公開用の一括起動スクリプトを含む手順全体については、新規GPU環境での通し実行は未確認です。再評価で2試行とも成功しなかった場合はエラーとして終了し、評価結果は出力先に残ります。

評価結果は`/content/pai_run/evaluation_new/evaluation/summary.json`で確認できます。

## 動画

提出用の編集済み動画は別途提供した`PAI_kojikoji_s_2x.mp4`です。1分48.1秒、搬送部分はシミュレーション時間の2倍速。推論待ち中は物理時間を停止しています。実時間の速度を表す動画ではありません。

`scripts/make_review.py`は新しい評価のフレームから2倍速の確認用動画を作ります。提出用の編集版とは説明画面のデザインが異なります。

## 実行時の保護

推論サーバーは`127.0.0.1`だけで待ち受けます。共有サーバーや外部公開用ではありません。ポート転送や公開トンネルは使用しないでください。リクエストのサイズ・形式・配列形状を確認し、受信にはタイムアウトを設けています。ROS/Gazebo起動時にはHugging Faceトークンを環境変数から除きます。
