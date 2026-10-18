# 実行時に生成されるファイルの開き方
(English translation follows below)

`RUN`は準備セルが作成する今回の作業フォルダ、`EVAL`は今回使用する評価フォルダを表すPython変数です。固定のURLではなく、実行日時によって実際のパスが変わります。以下のファイル名のリンクは、この開き方の説明へ移動します。ファイル本体への公開リンクではありません。

Colab左側のフォルダアイコン（ファイル）を開き、必要なら更新して、準備セルに表示された作業フォルダをたどってください。通常は `/content/pai_runs/実行日時/` の下です。ファイルのメニューからダウンロードできます。モデル重みはバイナリ形式なので、テキストとして読むファイルではありません。

## initial-checkpoint
### 初回学習の重み
`RUN/checkpoint/expert.safetensors`

新規学習の4が成功した場合に作成します。保存済みの追加学習モデルを復元して初回学習をスキップした場合、このファイルがないことは正常です。

## refined-checkpoint
### 追加学習の重み
`RUN/checkpoint_refined/expert.safetensors`

5の追加学習、または準備セルで保存済みモデルを復元した際に作成します。モデルなしの完成済み評価記録だけを再利用した場合は存在しないことがあります。

## review-video
### 提出用動画
`EVAL/review_2x.mp4`

7で生成し、セルの出力にも表示します。評価フォルダ名は実行方法・日時により異なります。

## run-origin
### 使用データの出所
`RUN/run_origin.json`

準備セルで作成します。Colabのファイル一覧で開いて内容を確認できます。

## Driveに保存した後
8が成功すると、今回の作業フォルダ全体を `MyDrive/PAI_results/` の下へ保存します。8が表示する保存先を確認し、[Google Drive](https://drive.google.com/drive/u/0/my-drive)でそのフォルダを開いてください。既存フォルダと同名の場合は別のバックアップ名になります。学習済み重みを開くために共有設定を「公開」にする必要はありません。

---

# English

`RUN` is the working folder created by preparation; `EVAL` is the evaluation folder used for this run. These are Python variables, not fixed URLs. Paths vary by execution time. Links to generated filenames lead to this guide, not to publicly accessible copies of the files.

In Colab, open the Files pane using the folder icon, refresh if needed, and navigate to the working folder printed by preparation, normally under `/content/pai_runs/<run timestamp>/`. Use the file menu to download a file. Model weights are binary files, not readable text documents.

- **Initial checkpoint:** `RUN/checkpoint/expert.safetensors` is created after successful new training in section 4. Its absence is normal when initial training is skipped in favor of restored refined weights.
- **Refined checkpoint:** `RUN/checkpoint_refined/expert.safetensors` is created by section 5 or restored during preparation. It may be absent when reusing complete evaluation records without model weights.
- **Submission video:** `EVAL/review_2x.mp4` is created and displayed in section 7. The evaluation folder name depends on the execution method and timestamp.
- **Data provenance:** `RUN/run_origin.json` is created during preparation and can be opened in Colab's Files pane.

After section 8 succeeds, the entire working folder is saved under `MyDrive/PAI_results/`. Check the destination printed by section 8 and open that folder in [Google Drive](https://drive.google.com/drive/u/0/my-drive). A different backup name is used if the destination already exists. You do not need to make model files public to access them.
