#!/usr/bin/env bash
set -euo pipefail
source /etc/os-release
case "$VERSION_CODENAME" in
  noble) ROS_DISTRO=jazzy; ROS_PYTHON=/usr/bin/python3.12; BRIDGE=ros-jazzy-ros-gz-bridge ;;
  jammy) ROS_DISTRO=humble; ROS_PYTHON=/usr/bin/python3.10; BRIDGE=ros-humble-ros-gzharmonic-bridge ;;
  *) echo "Supported: Ubuntu 22.04 / 24.04. Detected: $PRETTY_NAME"; exit 2 ;;
esac
export DEBIAN_FRONTEND=noninteractive
# Repair only the source file owned by this project, before the first update.
# ROS distributes signed APT metadata over HTTP; keep signed-by verification.
if [ -f /etc/apt/sources.list.d/pai-ros2.list ]; then
  sed -i 's|https://packages.ros.org/ros2/ubuntu|http://packages.ros.org/ros2/ubuntu|g' /etc/apt/sources.list.d/pai-ros2.list
fi
apt-get update
apt-get install -y curl gnupg ca-certificates locales software-properties-common
add-apt-repository -y universe
locale-gen en_US.UTF-8
curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/pai-ros-keyring.gpg
curl -fsSL https://packages.osrfoundation.org/gazebo.gpg -o /usr/share/keyrings/pai-gazebo-keyring.gpg
ARCH=$(dpkg --print-architecture)
echo "deb [arch=$ARCH signed-by=/usr/share/keyrings/pai-ros-keyring.gpg] http://packages.ros.org/ros2/ubuntu $VERSION_CODENAME main" > /etc/apt/sources.list.d/pai-ros2.list
echo "deb [arch=$ARCH signed-by=/usr/share/keyrings/pai-gazebo-keyring.gpg] https://packages.osrfoundation.org/gazebo/ubuntu-stable $VERSION_CODENAME main" > /etc/apt/sources.list.d/pai-gazebo.list
apt-get -o APT::Update::Error-Mode=any update
apt-get install -y "ros-$ROS_DISTRO-ros-base" "$BRIDGE" "${ROS_PYTHON##*/}" gz-harmonic git python3-scipy "ros-$ROS_DISTRO-xacro" python3-numpy python3-pil python3-yaml python3-reportlab fonts-ipafont-gothic ffmpeg libegl1 libgl1-mesa-dri xvfb xauth
printf '%s\n' "$ROS_DISTRO" > "$(dirname "$0")/ros_distro.txt"
printf '%s\n' "$ROS_PYTHON" > "$(dirname "$0")/ros_python.txt"
# Use the interpreter matching the ROS binary ABI, not Colab's python3 alias.
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1
export COLCON_PYTHON_EXECUTABLE="$ROS_PYTHON"
export AMENT_PYTHON_EXECUTABLE="$ROS_PYTHON"
set +u
source "/opt/ros/$ROS_DISTRO/setup.bash"
set -u
"$ROS_PYTHON" -c 'import sys, rclpy, numpy, PIL, reportlab; from sensor_msgs.msg import Image; print("ROS imports OK:", sys.executable, sys.version)'
# ROS vendor hooks can hide the OSRF Gazebo command YAML directory.
export GZ_CONFIG_PATH=/usr/share/gz
printf 'Gazebo executable: /usr/bin/gz; GZ_CONFIG_PATH=%s\n' "$GZ_CONFIG_PATH"
if ! /usr/bin/gz sim --versions; then
  echo 'Gazebo CLI diagnostics:'
  ls -l /usr/bin/gz /usr/share/gz || true
  dpkg-query -W gz-tools2 gz-sim8-cli libgz-sim8 || true
  exit 3
fi
echo 'Gazebo sim CLI OK'
