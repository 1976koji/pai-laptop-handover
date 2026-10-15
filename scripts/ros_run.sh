#!/usr/bin/env bash
set -euo pipefail
PROJECT=$(cd "$(dirname "$0")/../it_desk" && pwd)
DISTRO=$(cat "$PROJECT/ros_distro.txt")
ROS_PY=$(cat "$PROJECT/ros_python.txt")
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1
set +u
source "/opt/ros/$DISTRO/setup.bash"
set -u
export GZ_CONFIG_PATH=/usr/share/gz
SCRIPT=$1
shift
exec "$ROS_PY" "$PROJECT/$SCRIPT" "$@"
