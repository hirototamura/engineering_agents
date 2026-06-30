"""Headless SSOS: solar + EPS + ECLSS (no Qt crew GUI).

Single launch process tree so Ctrl+C shuts everything down cleanly.
"""
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    space_station_pkg = get_package_share_directory('space_station')

    solar_power = Node(
        package='space_station_eps',
        executable='solar_power',
        name='solar_power_node',
        output='screen',
    )

    eps = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(space_station_pkg, 'launch', 'eps.launch.py')
        ),
    )

    eclss = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(space_station_pkg, 'launch', 'eclss.launch.py')
        ),
    )

    return LaunchDescription([
        solar_power,
        eps,
        eclss,
    ])
