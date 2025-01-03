# Copyright 2022 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""testing of builder.py using pytest."""

import argparse
import logging
import os
import pathlib

import pytest
from rosdoc2.verbs.build.impl import main_impl, prepare_arguments

from .utils import do_test_full_package, do_test_package

logger = logging.getLogger('rosdoc2.test.builder')
DATAPATH = pathlib.Path('test/packages')


@pytest.fixture(scope='module')
def module_dir(tmp_path_factory):
    tmp_path_factory.mktemp('build', False)
    tmp_path_factory.mktemp('cross_references', False)
    tmp_path_factory.mktemp('output', False)
    return tmp_path_factory.getbasetemp()


def do_build_package(package_path, work_path, with_extension=False) -> None:
    build_dir = work_path / 'build'
    output_dir = work_path / 'output'
    cr_dir = work_path / 'cross_references'

    # Create a top level parser
    parser = prepare_arguments(argparse.ArgumentParser())
    args = [
        '-p', str(package_path),
        '-c', str(cr_dir),
        '-o', str(output_dir),
        '-d', str(build_dir),
    ]
    if with_extension:
        args.extend(['-y', str(pathlib.Path('test') / 'ex_test.yaml')])
    options = parser.parse_args(args)
    logger.info(f'*** Building package(s) at {package_path} with options {options}')

    # run rosdoc2 on the package
    main_impl(options)


def test_never_sphinx_apidoc(module_dir):
    """Tests of never_run_sphinx_apidoc."""
    PKG_NAME = 'never_sphinx_apidoc'
    do_build_package(DATAPATH / PKG_NAME, module_dir)

    includes = [
        PKG_NAME,
    ]

    excludes = ['python api']  # No python api generated since never_run_sphinx_apidoc is set

    do_test_package(PKG_NAME, module_dir,
                    includes=includes, excludes=excludes)


def test_never_doxygen(module_dir):
    """Tests of never_run_doxygen."""
    PKG_NAME = 'never_doxygen'
    do_build_package(DATAPATH / PKG_NAME, module_dir)

    includes = [
        PKG_NAME,
    ]

    excludes = ['c++ api']  # No c++ api since never_run_doxygen set

    do_test_package(PKG_NAME, module_dir,
                    includes=includes, excludes=excludes)


def test_minimum_package(module_dir):
    """Tests of a package containing as little as possible."""
    PKG_NAME = 'minimum_package'
    do_build_package(DATAPATH / PKG_NAME, module_dir)

    includes = [
        PKG_NAME,
    ]
    excludes = [
        'classes and structs',  # only found in C++ projects
    ]
    file_includes = [
        'search.html',
    ]
    file_excludes = [
        'generated/index.html',  # empty packages have no generated content
    ]
    links_exist = [
        'genindex.html',
    ]
    do_test_package(PKG_NAME, module_dir,
                    includes=includes,
                    excludes=excludes,
                    file_includes=file_includes,
                    file_excludes=file_excludes,
                    links_exist=links_exist)


def test_full_package(module_dir):
    """Test a package with C++, python, and docs."""
    PKG_NAME = 'full_package'
    do_build_package(DATAPATH / PKG_NAME, module_dir)

    do_test_full_package(module_dir)


def test_default_yaml(module_dir):
    """Test a package with C++, python, and docs using specified default rosdoc2.yaml configs."""
    PKG_NAME = 'default_yaml'
    do_build_package(DATAPATH / PKG_NAME, module_dir, with_extension=True)

    do_test_full_package(module_dir, pkg_name=PKG_NAME)


def test_only_python(module_dir):
    """Test a pure python package."""
    PKG_NAME = 'only_python'
    # Use with_extension=True to show that nothing changes if the package is not there.
    do_build_package(DATAPATH / PKG_NAME, module_dir, with_extension=True)

    includes = [
        PKG_NAME,
    ]
    links_exist = ['only_python.python_node.html']
    do_test_package(PKG_NAME, module_dir,
                    includes=includes,
                    links_exist=links_exist)


def test_src_python(module_dir):
    PKG_NAME = 'src_python'
    do_build_package(DATAPATH / PKG_NAME, module_dir)

    includes = [
        'src_python package',
        'documentation in source',  # We found the documentation in doc/source
    ]
    links_exist = ['src_python.html', 'src_python.python_node.html']

    do_build_package(DATAPATH / PKG_NAME, module_dir)

    do_test_package(PKG_NAME, module_dir,
                    includes=includes,
                    links_exist=links_exist)


def test_false_python(module_dir):
    PKG_NAME = 'false_python'
    do_build_package(DATAPATH / PKG_NAME, module_dir)

    excludes = ['python api']
    includes = [
        'I say I am python, but no actual python',
        'this is documentation'  # the title of included documentation
    ]
    links_exist = [
        'user_docs.html',  # Found docs in a non-standard location
        'docs/moredocs/more1.html'  # Found subdirectory in non-standard location
    ]

    do_test_package(PKG_NAME, module_dir,
                    includes=includes,
                    excludes=excludes,
                    links_exist=links_exist)


def test_invalid_python_source(module_dir):
    PKG_NAME = 'invalid_python_source'
    do_build_package(DATAPATH / PKG_NAME, module_dir, with_extension=True)

    excludes = ['python api']
    includes = [
        'This packages incorrectly specifies python source',
        'this is in a funny place',  # Documentation found using extended yaml
    ]

    do_test_package(PKG_NAME, module_dir,
                    includes=includes,
                    excludes=excludes)


def test_too_many_python_packages(module_dir):
    PKG_NAME = 'too_many_python_packages'
    do_build_package(DATAPATH / PKG_NAME, module_dir)

    excludes = ['python api']
    includes = ['Too many unspecified python packages']

    do_test_package(PKG_NAME, module_dir,
                    includes=includes,
                    excludes=excludes)


def test_only_messages(module_dir):
    """Test a package only containing messages."""
    PKG_NAME = 'only_messages'

    # This tests that run succeeds even if rosdistro entry is missing.
    os.environ['ROS_DISTRO'] = 'rolling'
    do_build_package(DATAPATH / PKG_NAME, module_dir)

    includes = [
        PKG_NAME,
        'message definitions',
    ]
    links_exist = ['interfaces/msg/NumPwrResult.html']

    do_test_package(PKG_NAME, module_dir, includes=includes, links_exist=links_exist)


def test_basic_cpp(module_dir):
    """Test a basic C++ package."""
    PKG_NAME = 'basic_cpp'

    do_build_package(DATAPATH / PKG_NAME, module_dir)

    includes = [
        'a different title',  # changed in custom index.rst
        'basic_cpp_and_more',  # changed in custom config.py
    ]
    do_test_package(PKG_NAME, module_dir, includes=includes)

    # Previously, running rosdoc2 would create a 'generated' folder in the doc
    # subdirectory of the package. Directory refactoring should have eliminated
    # this.
    generated = pathlib.Path(DATAPATH / PKG_NAME / 'doc' / 'generated')
    assert not generated.exists(), \
        'Building should not create a "generated" directory in package/doc'


def test_has_sphinx_sourcedir(module_dir):
    PKG_NAME = 'has_sphinx_sourcedir'
    do_build_package(DATAPATH / PKG_NAME, module_dir)

    includes = [
        'i defined sphinx_sourcedir'
    ]
    excludes = [
        'standards.html',  # We override normal rosdoc2, so this should be missing.
    ]
    links_exist = [
        'moredocs/more1.html',  # Documentation in a subdirectory
    ]

    do_test_package(PKG_NAME, module_dir,
                    includes=includes,
                    excludes=excludes,
                    links_exist=links_exist)

    do_test_package(PKG_NAME, module_dir)


def test_empty_doc_dir(module_dir):
    # This package is run with an extended rosdoc2.yaml setting that adds all of the
    # default rosdoc2.yaml settings to the extended yaml.
    PKG_NAME = 'empty_doc_dir'
    do_build_package(DATAPATH / PKG_NAME, module_dir, with_extension=True)

    includes = [
        'package with an empty doc directory',  # The package description
    ]
    excludes = [
        'documentation'  # We should not show empty documentation
    ]
    links_exist = [
        'standards.html',  # We still show the package
    ]

    do_test_package(PKG_NAME, module_dir,
                    includes=includes,
                    excludes=excludes,
                    links_exist=links_exist)

    do_test_package(PKG_NAME, module_dir)


def test_src_alt_python(module_dir):
    PKG_NAME = 'src_alt_python'
    do_build_package(DATAPATH / PKG_NAME, module_dir, with_extension=True)

    includes = ['python api']  # We found the python source with the extended yaml
    links_exist = ['dummy.html']  # We found python source with extended yaml
    do_test_package(PKG_NAME, module_dir,
                    includes=includes,
                    links_exist=links_exist)


def test_ignore_doc(module_dir):
    """Tests of a package with doc directory, but rosdoc2.yaml says ignore."""
    PKG_NAME = 'ignore_doc'
    do_build_package(DATAPATH / PKG_NAME, module_dir)

    excludes = ['do not show']

    do_test_package(PKG_NAME, module_dir, excludes=excludes)


def test_rclcpp(module_dir):
    """Tests of repo url lookup from a known standard package."""
    PKG_NAME = 'rclcpp'
    os.environ['ROS_DISTRO'] = 'rolling'
    do_build_package(DATAPATH / PKG_NAME, module_dir)

    includes = [
        PKG_NAME,
    ]

    links_exist = ['https://github.com/ros2/rclcpp.git']  # Found repo url from rosdistro.
    do_test_package(PKG_NAME, module_dir,
                    includes=includes, links_exist=links_exist)


def test_user_jinja_root(module_dir):
    PKG_NAME = 'user_jinja_root'
    do_build_package(DATAPATH / PKG_NAME, module_dir)

    includes = [
        PKG_NAME,
        'extra user link',  # a non-standard link from a user-supplied index.rst.jinja
    ]

    do_test_package(PKG_NAME, module_dir,
                    includes=includes)


def test_user_jinja_sphinx_sourcedir(module_dir):
    PKG_NAME = 'user_jinja_sphinx_sourcedir'
    do_build_package(DATAPATH / PKG_NAME, module_dir)

    includes = [
        PKG_NAME,
        'extra user link',  # a non-standard link from a user-supplied index.rst.jinja
    ]

    do_test_package(PKG_NAME, module_dir,
                    includes=includes)
