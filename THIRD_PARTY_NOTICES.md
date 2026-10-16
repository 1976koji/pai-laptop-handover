# Third-party assets and attribution

The repository's MIT license applies to original project code. It does not relicense upstream robot assets, model weights, datasets, or dependencies.

- OpenArm description: https://github.com/enactic/openarm_description
  - The recorded manifest identifies Apache-2.0. `prepare_robot.py` downloads the pinned repository and retains its license in the asset copy. Review upstream LICENSE/NOTICE files before redistributing derived assets.
  - Changes: custom support adapters, removal of stock gripper housing/fingers in the generated simulation, collision-mesh reflection handling, idealized gravity compensation. Not an endorsement by the manufacturer.
- LeRobot: https://github.com/huggingface/lerobot
  - Used package version: `0.6.1`. Its license and dependencies retain their upstream terms.
- PI05 base weights: https://huggingface.co/lerobot/pi05_base
  - Base weights and fine-tuned weights are not included in this repository. Follow the model's terms separately.
- PaliGemma tokenizer: https://huggingface.co/google/paligemma-3b-pt-224
  - Access may require acceptance of its terms. Never commit access tokens.
- ROS 2, Gazebo, PyTorch, NumPy, SciPy, Pillow and other runtime dependencies retain their respective licenses.

Gazebo renderings in the report/video depict the above robot assets. Project design, code development, debugging and document preparation used generative-AI assistance; empirical claims are based on recorded simulator runs, not generated robot footage.
