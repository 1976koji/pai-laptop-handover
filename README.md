# オフィスなどにおけるノート型パソコン搬送に向けた双腕ロボットの基礎検証

(English translation follows below)

ROS 2・Gazebo・LeRobot $\pi_{0.5}$を用い、将来の情報システム窓口での貸出・受け渡しに向けた初期段階の搬送を検証します。搬送物は、ノート型パソコンを想定したケース形状の簡略化モデルです。ノート型パソコンの詳細構造や実機の物性を再現したものではありません。

Physical AI 応用1 最終課題 / OmniCampus account: **kojikoji_s**

## 本プロジェクトで検証すること

Gazeboの固定環境内で、OpenArm由来の双腕ロボットが搬送物を支持し、持ち上げ、受取台に置き、両支持具を退避させる一連の動作を検証します。AIと通常制御の役割分担は「学習と制御」、試行結果と評価条件は「開発時に記録した結果」に示します。

## 学習と制御

| 項目 | 実施内容 |
|---|---|
| ロボット | OpenArm V2由来の14関節モデル、独自の搬送物支持板 |
| 物理環境 | ROS 2 + Gazebo Harmonic、接触支持による搬送 |
| 基盤モデル | LeRobot `lerobot/pi05_base`、revision固定 |
| 学習環境 | Google ColabのA100 GPU（GPUメモリ80GB）、ハイメモリ設定、float32。GPUメモリとシステムRAMは別の資源 |
| 教師データ | 開発時の記録：学習23成功試行、検証6成功試行。収集結果は実行ごとに確認 |
| 追加学習の検証損失 | 開発時の記録：0.01913 → 0.01530。搬送成功率ではない |
| AIの役割 | 画像・関節状態・指示から関節目標を提案し、射影後の進行係数を決める |
| 通常制御の役割 | 経路、工程順序、双腕同期、関節制限と安定確認 |

学習済み関節目標を手先変位へ変換し、経路の次の目標方向へ射影します。進行係数は0〜1。ゼロ・負の射影では前進しません。教師制御への自動切替や最低限の自動前進量は使用していません。推論待ちの間はGazeboの物理シミュレーションの進行を一時停止します。詳細は[`cooperative.py`](it_desk/cooperative.py)と[`episode.py`](it_desk/episode.py)を参照してください。

## 学習・推論を行う箇所

**学習はノートブックの4・5、推論は6で行います。実行する場合はいずれもColabのGPUを使用します。** Google Driveの保存済みデータを使用する場合、不要な学習は自動で省略し、揃っている評価記録は再利用します。

| 段階 | 主なプログラム | 処理 |
|---|---|---|
| 3 教師データ収集 | `it_desk/collect.py` | 設計済みの教師制御でGazeboのロボットを動かし、画像・関節状態・正解動作を収集。この段階ではモデルを学習しません。 |
| 4 初回学習 | `it_desk/train.py` | 成功した教師データを用い、事前学習済み$\pi_{0.5}$の動作生成部分を500ステップ追加学習します。 |
| 5 追加学習 | `it_desk/train_refine.py` | 4の重みを引き継ぎ、さらに1,000ステップ学習します。 |
| 6 評価・推論 | `scripts/evaluate.py` → `it_desk/policy.py` | 学習済み重みを読み込み、2視点の画像・関節状態・タスク指示から、次の関節目標の列を予測します。評価中は重みを更新しません。 |

追加学習した重みは、実行フォルダ内の`checkpoint_refined/expert.safetensors`に保存され、6の推論時に読み込まれます。

[`it_desk/episode.py`](it_desk/episode.py)が制御ループを実行します。前節の進行係数の計算は、このループから呼び出す[`it_desk/cooperative.py`](it_desk/cooperative.py)が担当します。

## 開発時に記録した結果

[提出動画（YouTube）](https://www.youtube.com/watch?v=OnbQVtdJNwU)は、開発時に確認した2条件で改めて実行した搬送記録です。長さは**1分39秒（99秒）、シミュレーション時間基準の2倍速**です。

評価条件は[`it_desk/run_hybrid.py`](it_desk/run_hybrid.py)の`main()`内の`trials`で指定しています。`seed=900`は`developer`、`seed=901`は`standard`に対応します。ノートブックの6から`scripts/evaluate.py`を通じてこの2試行を実行し、結果は評価フォルダ内の`evaluation/summary.json`に記録します。seedは`world.py`の初期位置の乱数と、`episode.py`から渡す推論ノイズの乱数に使用します。

以下の数値は開発時の診断JSONに基づく記録であり、2026年10月16日のUATの実測値ではありません。

| seed | 指示 | シミュレーション時間 | 最大持上げ量 | 結果 |
|---|---|---:|---:|---|
| 900 | developer | 91.20秒 | 13.0 cm | 成功 |
| 901 | standard | 93.46秒 | 14.3 cm | 成功 |

成功には持ち上げ、目標位置への水平設置、両支持具の離脱、2秒以上の安定が必要です。元データは別途保存した診断ZIPにあります（本リポジトリには未公開）。これらは開発中に確認した配置であり、未知配置への汎化や実機の性能は未検証です。

## 開発経緯と位置付け

開発初期には、タスク固有データで追加学習した $\pi_{0.5}$ 方策が予測した関節目標を、関節ごとの移動量制限などを介して制御器へ渡していました。しかし、左右の支持位置が崩れ、搬送物が落下しました。そこで、前述の双腕協調制御へ変更し、限られた開発期間では、初期配置と搬送経路を限定したうえで、学習済みモデルを進行量の調整に組み込み、搬送を成功させることを目標としました。

本課題は、AIを用いた自動化の第一段階として、シミュレーションによる教師データ生成、追加学習、制御への統合、搬送テストまでを一通り実装したものです。その過程で必要となった対策と制約を整理し、次に検証すべき課題を明確にした点を成果として位置付けています。

2026年10月18日、提出動画の作成に用いた版について、利用者がUAT（ユーザー受入テスト）の完了を確認しました。

## 実行方法

1. [PAI_submission.ipynb](notebooks/PAI_submission.ipynb)をダウンロード。
2. Colabで「ファイル」→「ノートブックをアップロード」から開く。
3. ランタイムを**A100・ハイメモリ**に設定。
4. **上から順に、各セルの完了を確認しながら実行**。最初のプルダウンで、Driveの保存済みデータ（既定は利用可能な最新版）、保存日時の指定、または新規学習を選択。認証を求められたら自分のHugging Face読み取りトークンを入力。

## 限界

- 学習済みモデルと教師データは同梱していません。
- 腕は搬送物の脇から開始。待機姿勢からの接近、移動台車、複数在庫探索、人の受領確認は未実装。
- 搬送物は支持板との物理接触で支えます。搬送物とロボットを固定接続する設定は使用していません。
- 今回は搬送動作の基礎検証に範囲を絞り、ロボットを構成する各部品（リンク）に重力が作用しない設定にしています。実機で腕の自重を支えるための重力補償制御を再現したものではありません。また、ロボット自身の部品同士の衝突を扱う「自己衝突」の設定を無効にしているため、実機で部品同士が干渉せず動けることを、この検証だけで確認したわけではありません。
- `ready_for_collection`は受取台への準備完了であり、貸出処理完了ではない。

## ライセンスと作成支援

自作コードは[MIT License](LICENSE)。ロボット資産、モデル、依存ソフトウェアは各配布元の条件に従います。[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)を参照してください。

設計・コード・デバッグ・資料作成には生成AIの支援を利用しました。実験結果と動画は、実際のモデル学習およびGazebo上でのロボット制御の実行記録に基づきます。

---

## English

# Preliminary validation of a dual-arm robot for laptop transport in office settings

Using ROS 2, Gazebo and LeRobot $\pi_{0.5}$, this project validates an initial transport task toward future laptop lending and handover at an IT service desk. The object is a simplified case-shaped model representing a laptop; it does not reproduce a laptop's detailed structure or real material properties.

Physical AI Advanced 1 Final Project / OmniCampus account: **kojikoji_s**

## What this project demonstrates

In a fixed Gazebo environment, an OpenArm-based dual-arm robot supports the object, lifts it, places it on a receiving platform, and withdraws both supports. The roles of AI and conventional control are described under “Training and control”; trial outcomes and conditions are listed under “Recorded development results.”

## Training and control

| Item | Implementation |
|---|---|
| Robot | 14-joint model derived from OpenArm V2, with custom support plates |
| Physics environment | ROS 2 + Gazebo Harmonic; transport through contact support |
| Base model | LeRobot `lerobot/pi05_base`, pinned revision |
| Training environment | Google Colab A100 GPU (80 GB GPU memory), high-RAM setting, float32. GPU memory and system RAM are separate resources |
| Teacher data | Development record: 23 successful training trials and 6 successful validation trials. Check each run's collection results |
| Refinement validation loss | Development record: 0.01913 → 0.01530; this is not a transport success rate |
| AI role | Propose joint targets from images, joint state and instructions; determine the progress coefficient after projection |
| Conventional-control role | Path, phase order, dual-arm synchronization, joint limits and stability checks |

Predicted joint targets are converted to hand displacements and projected onto the direction of the next path target. The progress coefficient is bounded to 0–1. Zero or negative projection produces no forward progress. No teacher fallback or minimum automatic forward motion is used. Gazebo physics pauses while waiting for inference. See [cooperative.py](it_desk/cooperative.py) and [episode.py](it_desk/episode.py).

## Where training and inference occur

**Training runs in notebook sections 4 and 5; inference runs in section 6. Both use the Colab GPU when executed.** When saved Drive data is selected, unnecessary training is skipped and complete recorded evaluations are reused automatically.

| Stage | Main program | Processing |
|---|---|---|
| 3 Teacher data collection | `it_desk/collect.py` | Runs the designed teacher controller in Gazebo and records images, joint states and target actions. No model training occurs here. |
| 4 Initial training | `it_desk/train.py` | Fine-tunes the action-generation component of pretrained $\pi_{0.5}$ for 500 steps on successful demonstrations. |
| 5 Additional training | `it_desk/train_refine.py` | Continues from section 4 weights for another 1,000 steps. |
| 6 Evaluation/inference | `scripts/evaluate.py` → `it_desk/policy.py` | Loads trained weights and predicts sequences of joint targets from two camera images, joint state and task instructions. Weights are not updated during evaluation. |

Refined weights are saved as `checkpoint_refined/expert.safetensors` within the run folder and loaded for inference in section 6.

[`it_desk/episode.py`](it_desk/episode.py) executes the control loop. The progress coefficient described in the preceding section is calculated by [`it_desk/cooperative.py`](it_desk/cooperative.py), which is called from that loop.

## Recorded development results

The [submitted YouTube video](https://www.youtube.com/watch?v=OnbQVtdJNwU) records new executions of two conditions checked during development. It is **1 minute 39 seconds (99 seconds), at 2x simulation-time speed**.

Evaluation conditions are specified by `trials` in `main()` of [it_desk/run_hybrid.py](it_desk/run_hybrid.py). Seed 900 corresponds to `developer`, and seed 901 to `standard`. Notebook section 6 executes these two trials through `scripts/evaluate.py`, with results saved as `evaluation/summary.json` within the evaluation output folder. The seeds control initial-position randomness in `world.py` and inference-noise randomness passed from `episode.py`.

The following values are development diagnostic records, not measurements from the October 16, 2026 UAT.

| Seed | Instruction | Simulation time | Maximum lift | Result |
|---|---|---:|---:|---|
| 900 | developer | 91.20 s | 13.0 cm | Success |
| 901 | standard | 93.46 s | 14.3 cm | Success |

Success requires lifting, level placement at the target, withdrawal of both supports, and at least two seconds of stability. Source records are in separately saved diagnostic ZIPs, not published in this repository. These placements were also checked during development; generalization to unseen placements and real-hardware performance remain untested.

## Development experience and project scope

In the initial implementation, joint targets predicted by the task-fine-tuned $\pi_{0.5}$ policy were passed to the controller through safeguards such as per-joint movement limits. The left and right support positions nevertheless lost coordination, and the object fell. We therefore adopted the coordinated control described above. Within the limited development period, the goal was to complete transport with restricted initial placements and a predefined path, while using the learned model to adjust progress.

This project represents a first stage of AI-assisted automation: implementing the full sequence from simulated demonstration generation and fine-tuning to control integration and transport testing. Its contribution is to document the measures and constraints encountered during this process and identify the next questions to test.

On October 18, 2026, the user confirmed completion of user acceptance testing (UAT) for the version used to produce the submitted video.

## How to run

1. Download [PAI_submission.ipynb](notebooks/PAI_submission.ipynb).
2. In Colab, choose **File → Upload notebook**.
3. Select an **A100 GPU and high-RAM** runtime.
4. **Run cells in order, confirming each completes.** In the initial dropdown, choose saved Drive data (latest usable data by default), a specific saved run, or new collection/training. If prompted, enter your own Hugging Face read token.

## Limitations

- Trained weights and teacher data are not included.
- Arms start beside the object. Home-to-object approach, a mobile base, multiple-item inventory search and human receipt confirmation are not implemented.
- The object is supported through physical contact with the support plates. It is not attached to the robot by a fixed joint.
- To focus on preliminary transport validation, gravity is disabled for the robot's individual rigid components (links). This does not reproduce the gravity-compensation control needed to support the arms' own weight on real hardware. Self-collision, which handles collisions between the robot's own components, is also disabled. These tests therefore do not establish that the same motions would avoid interference between components on a real robot.
- `ready_for_collection` means the object is ready on the receiving platform; it does not mean a lending transaction is complete.

## License and creation assistance

Original code is released under the [MIT License](LICENSE). Robot assets, model weights and dependencies remain subject to their respective terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Generative AI assisted with design, coding, debugging and documentation. Experimental results and videos are based on actual model training and recorded robot-control execution in Gazebo.
