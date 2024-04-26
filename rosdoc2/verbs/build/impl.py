# Copyright 2020 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import os
import shutil
import sys

from catkin_pkg.package import has_ros_schema_reference
from catkin_pkg.package import InvalidPackage
from catkin_pkg.package import package_exists_at
from catkin_pkg.package import parse_package
from rosdoc2.slugify import slugify

from .inspect_package_for_settings import inspect_package_for_settings

logging.basicConfig(format='[%(name)s] [%(levelname)s] %(message)s', level=logging.INFO)
logger = logging.getLogger('rosdoc2')

DEFAULT_BUILD_DIR = 'docs_build'
DEFAULT_OUTPUT_DIR = 'docs_output'
DEFAULT_CROSS_REFERENCE_DIR = 'cross_reference'


def get_package(path):
    """Get the ROS package for the given path."""
    if not package_exists_at(path):
        raise RuntimeError(f"Failed to find a ROS package at given path '{path}'")

    try:
        package = parse_package(path)
    except (AssertionError, InvalidPackage) as e:
        if has_ros_schema_reference(path):
            raise RuntimeError(f"Failed to parse ROS package manifest in '{path}': {e}")
        else:
            raise RuntimeError(f"Failed to parse potential ROS package manifest in '{path}': {e}")
        return None

    package.evaluate_conditions(os.environ)
    return package


def prepare_arguments(parser):
    """Add command-line arguments to the argparse object."""
    parser.add_argument(
        '--package-path',
        '-p',
        required=True,
        help='path to the ROS package',
    )
    parser.add_argument(
        '--build-directory',
        '-b',
        help='UNUSED, to be removed at some time after September 1st, 2024',
    )
    parser.add_argument(
        '--install-directory',
        '-i',
        help='install directory of the package',
    )
    parser.add_argument(
        '--cross-reference-directory',
        '-c',
        default=DEFAULT_CROSS_REFERENCE_DIR,
        help='directory containing cross reference files, like tag files and inventory files',
    )
    parser.add_argument(
        '--base-url',
        '-u',
        default='http://docs.ros.org/en/rolling/p',
        help='The base url where the package docs will be hosted, used to configure tag files.',
    )
    parser.add_argument(
        '--output-directory',
        '-o',
        default=DEFAULT_OUTPUT_DIR,
        help='directory to output the documenation artifacts into',
    )
    parser.add_argument(
        '--doc-build-directory',
        '-d',
        default=DEFAULT_BUILD_DIR,
        help='directory to setup build prefix'
    )
    parser.add_argument(
        '--debug',
        default=False,
        action='store_true',
        help='enable more output to debug problems'
    )
    return parser


def main(options):
    """Execute the program, catching errors."""
    try:
        return main_impl(options)
    except Exception as e:  # noqa: B902
        if options.debug:
            raise
        else:
            sys.exit(str(e))


def main_impl(options):
    """Execute the program."""
    # Locate and parse the package's package.xml.
    package = get_package(options.package_path)

    if options.build_directory is not None:
        logger.warn(
            'The --build-directory option (-b) is unused and will be removed in a future version')

    if options.install_directory is not None:
        # Check that the install directory exists.
        if not os.path.exists(options.install_directory):
            sys.exit(
                f"Error: given install directory '{options.install_directory}' does not exist")

    # Inspect package for additional settings, using defaults if none found.
    tool_settings, builders = inspect_package_for_settings(
        package,
        options,
    )

    # Create the cross reference directory if it doesn't exist.
    os.makedirs(os.path.join(options.cross_reference_directory, package.name), exist_ok=True)

    # Generate the doc build directory.
    package_doc_build_directory = os.path.join(options.doc_build_directory, package.name)
    os.makedirs(package_doc_build_directory, exist_ok=True)

    # Generate the "output staging" directory.
    output_staging_directory = os.path.join(package_doc_build_directory, 'output_staging')
    if os.path.exists(output_staging_directory):
        # Delete this directory because it is temporary and will cause "file collision"
        # false positives if the tool fails to run to completion.
        shutil.rmtree(output_staging_directory)
    os.makedirs(output_staging_directory)

    # Generate the package header content.
    pass

    # Run each builder.
    for builder in builders:
        # This is the working directory for the builder.
        doc_build_folder = os.path.join(package_doc_build_directory, slugify(builder.name))
        # This is the directory into which the results of the builder will be moved into.
        builder_destination = os.path.join(output_staging_directory, builder.output_dir)
        # Run the builder, get the directory where the artifacts were placed.
        # This should be inside the doc_build_folder, but might be a subfolder.
        doc_output_directory = builder.build(
            doc_build_folder=doc_build_folder,
            output_staging_directory=output_staging_directory,
        )
        if doc_output_directory is None:
            # This builder did not generate any output.
            logger.info(
                f"Note: the builder '{builder.name} ({builder.builder_type})' "
                'did not generate any output to be copied into the destination.')
            continue
        assert os.path.exists(doc_output_directory), \
            f'builder gave invalid doc_output_directory: {doc_output_directory}'
        # Move documentation artifacts from the builder into the output staging.
        # This is additionally in a subdirectory dictated by the output directory part of the
        # builder configuration.
        builder.move_files(
            source=doc_output_directory,
            destination=builder_destination)

    # If enabled, create package index.
    if tool_settings.get('generate_package_index', True):
        pass

    # Move staged files to user provided output directory.
    package_output_directory = os.path.join(options.output_directory, package.name)
    logger.info(f"Moving files to final destination in '{package_output_directory}'.")
    for root, dirs, files in os.walk(output_staging_directory):
        for item in dirs + files:
            source = os.path.abspath(os.path.join(root, item))
            destination = \
                os.path.abspath(os.path.join(package_output_directory, item))
            if os.path.isdir(destination):
                # shutil.move behaves in a way such that if the destination exists
                # and is a directory, it would copy the source directory into it,
                # rather than replacing its contents or appending to it.
                # So deleting it first will prevent that.
                shutil.rmtree(destination)
            shutil.move(source, destination)
        break

    return 0
