# Dual-arm laptop-case delivery for an IT service desk

ROS 2・Gazebo・LeRobot π0.5を用いた情報システム窓口向け双腕PCケース搬送。

Physical AI 応用1 最終課題 / OmniCampus account: **kojikoji_s**

## What this project demonstrates

A learned PI05 model proposes actions from two camera views, joint state and a task instruction. Its proposal determines forward progress along a **classically designed bimanual path**. The OpenArm-based robot supports a laptop case, lifts it, places it on a pickup stand, and withdraws both supports in Gazebo. The recorded final configuration completed **2 of 2 development trials**.

This is a fixed-cell simulation, not mobile shelf retrieval or direct human handover. Path geometry and sequencing are not learned. Physics pauses during policy inference, so the video does not demonstrate real-time operation. No teacher fallback or minimum automatic forward motion is used.

## 提出物

- 提出用動画は別ファイルで提供。108.1秒、搬送部分はシミュレーション時間の**2倍速**。
- 説明資料PDFは別ファイルで提供。
- 編集用Wordは別ファイルで提供。
- 実装：[`it_desk/`](it_desk/)、実行補助：[`scripts/`](scripts/)
- [Colab用ノートブック](notebooks/PAI_submission.ipynb) / [実行手順](docs/REPRODUCE.md)

YouTubeへのアップロードとOmniCampusへの提出は別途必要です。チャンネルの概要URLは動画の提出URLの代わりにはなりません。YouTubeタイトルは`PAI最終課題_kojikoji_s`、公開または限定公開を指定してください。

## 学習と制御

| 項目 | 実施内容 |
|---|---|
| ロボット | OpenArm V2由来の14関節モデル、独自のケース支持板 |
| 物理環境 | ROS 2 + Gazebo Harmonic、接触支持による搬送 |
| 基盤モデル | LeRobot `lerobot/pi05_base`、revision固定 |
| 学習環境 | Google Colab、NVIDIA A100 80GB、float32 |
| 教師データ | 学習23成功試行、検証6成功試行 |
| 最適化 | 初回500ステップ + 重みを引き継ぐ追加1,000ステップ |
| 追加学習の検証損失 | 0.01913 → 0.01530。搬送成功率ではない |
| AIの役割 | 画像・関節状態・指示から関節目標を提案し、射影後の進行係数を決める |
| 通常制御の役割 | 経路、工程順序、双腕同期、関節制限と安定確認 |

学習済み関節目標を手先変位へ変換し、経路の次の目標方向へ射影します。進行係数は0〜1。ゼロ・負の射影では前進しません。詳細は[`cooperative.py`](it_desk/cooperative.py)を参照してください。

## 記録した結果

| seed | 指示 | シミュレーション時間 | 最大持上げ量 | 結果 |
|---|---|---:|---:|---|
| 900 | developer | 91.20秒 | 13.0 cm | 成功 |
| 901 | standard | 93.46秒 | 14.3 cm | 成功 |

成功には持ち上げ、目標位置への水平設置、両支持具の離脱、2秒以上の安定が必要です。元データは別途保存した診断ZIPにあります（本リポジトリには未公開）。これらは開発中に確認した配置であり、未知配置への汎化や実機の性能は未検証です。

以前の直接関節制御では落下が生じました。学習済みモデルだけで全軌道を制御できたと主張するものではありません。先行する進行量無効化試験では動作しませんでしたが、一定進行量やランダム出力に対する優位性は未検証です。

## 実行と再現性

Colabで[`notebooks/PAI_submission.ipynb`](notebooks/PAI_submission.ipynb)を開き、[手順](docs/REPRODUCE.md)に沿って実行します。環境構築、データ収集、学習、評価の順に、各段階の完了を確認して実行してください。

重みと教師画像データはGitに含めていません。教師データ収集と学習から実行できます。パッケージ配布の変化や物理計算の差により同一結果は保証しません。

公開用のラッパーと整理済みノートブックは静的検査の対象です。成功時の制御本体は記録版から取得していますが、整理済み手順のGPU上での通し再実行は未実施です。学習・推論・Gazebo実行済みの証拠と、公開用整理時の検査を区別します。

## 限界

- 腕はケース横から開始。待機姿勢からの接近、移動台車、複数在庫探索、人の受領確認は未実装。
- 支持板で接触支持。ケースの固定接続・瞬間移動は使用しない。
- ロボットの重力補償はリンク重力無効化による理想化。自己衝突は無効。
- `ready_for_collection`は受取台への準備完了であり、貸出処理完了ではない。

## ライセンスと作成支援

自作コードは[MIT License](LICENSE)。ロボット資産、モデル、依存ソフトウェアは各配布元の条件に従います。[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)を参照してください。

設計、コード、デバッグ、資料作成には生成AIの支援を利用しました。結果は実際の学習とGazeboの実行記録に基づきます。生成したロボット映像を実験映像として使用していません。
