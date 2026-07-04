"""Headless SSOS: solar + EPS only (no ECLSS crew GUI).

Use when ARS/ECLSS nodes need DDCU power but you do not want the full stack:

    ros2 launch /root/ssos-eps.launch.py

Mounted from host via scripts/ssos/mac/ssos-run*.sh.
"""
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    space_station_pkg = get_package_share_directory("space_station")

    solar_power = Node(
        package="space_station_eps",
        executable="solar_power",
        name="solar_power_node",
        output="screen",
    )

    eps = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(space_station_pkg, "launch", "eps.launch.py")
        ),
    )

    return LaunchDescription([
        solar_power,
        eps,
    ])
