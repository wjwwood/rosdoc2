# Copyright 2020 Open Source Robotics Foundation, Inc.
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

import logging
import os

import yaml

from .build_context import BuildContext
from .builders import create_builder_by_name
from .create_format_map_from_package import create_format_map_from_package
from .parse_rosdoc2_yaml import parse_rosdoc2_yaml

logger = logging.getLogger('rosdoc2')

DEFAULT_ROSDOC_CONFIG_FILE = """\
## Default configuration, generated by rosdoc2.

## This 'attic section' self-documents this file's type and version.
type: 'rosdoc2 config'
version: 1

---

settings: {{
    ## This setting is relevant mostly if the standard Python package layout cannot
    ## be assumed for 'sphinx-apidoc' invocation. The user can provide the path
    ## (relative to the 'package.xml' file) where the Python modules defined by this
    ## package are located.
    # python_source: '{package_name}',

    ## This setting, if true, attempts to run `doxygen` and the `breathe`/`exhale`
    ## extensions to `sphinx` regardless of build type. This is most useful if the
    ## user would like to generate C/C++ API documentation for a package that is not
    ## of the `ament_cmake/cmake` build type.
    # always_run_doxygen: false,

    ## This setting, if true, attempts to run `sphinx-apidoc` regardless of build
    ## type. This is most useful if the user would like to generate Python API
    ## documentation for a package that is not of the `ament_python` build type.
    # always_run_sphinx_apidoc: false,

    ## This setting, if provided, will override the build_type of this package
    ## for documentation purposes only. If not provided, documentation will be
    ## generated assuming the build_type in package.xml.
    # override_build_type: '{package_build_type}',
}}
builders:
    ## Each stanza represents a separate build step, performed by a specific 'builder'.
    ## The key of each stanza is the builder to use; this must be one of the
    ## available builders.
    ## The value of each stanza is a dictionary of settings for the builder that
    ## outputs to that directory.
    ## Keys in all settings dictionary are:
    ##  * 'output_dir' - determines output subdirectory for builder instance
    ##                   relative to --output-directory
    ##  * 'name' - used when referencing the built docs from the index.

    - doxygen: {{
        # name: '{package_name} Public C/C++ API',
        # output_dir: 'generated/doxygen',
        ## file name for a user-supplied Doxyfile
        # doxyfile: null,
        ## additional statements to add to the Doxyfile, list of strings
        # extra_doxyfile_statements: [],
      }}
    - sphinx: {{
        # name: '{package_name}',
        ## This path is relative to output staging.
        # doxygen_xml_directory: 'generated/doxygen/xml',
        # output_dir: '',
        ## If sphinx_sourcedir is specified and not null, then the documentation in that folder
        ## (specified relative to the package.xml directory) will replace rosdoc2's normal output.
        ## If sphinx_sourcedir is left unspecified, any documentation found in the doc/ or
        ## doc/source/ folder will still be included by default, along with other relevant package
        ## information.
        # sphinx_sourcedir: null,
        ## Directory (relative to the package.xml directory) where user documentation is found. If
        ## documentation is in one of the standard locations (doc/ or doc/source) this is not
        ## needed. Unlike sphinx_sourcedir, specifying this does not override the standard rosdoc2
        ## output, but includes this user documentation along with other items included by default
        ## by rosdoc2.
        # user_doc_dir: 'doc'
      }}
"""


def inspect_package_for_settings(package, tool_options):
    """
    Inspect the given package for additional documentation build settings.

    Uses default settings if not otherwise specified by the package.

    If there is a configuration file, then it is used, but if no configuration
    file then a default file is used.

    The default file would look like this:

    {DEFAULT_ROSDOC_CONFIG_FILE}

    :return: dictionary of documentation build settings
    """
    rosdoc_config_file = None
    rosdoc_config_file_name = None
    # Check if the package.xml exports a settings file.
    for export_statement in package.exports:
        if export_statement.tagname == 'rosdoc2':
            config_file_name = export_statement.content
            full_config_file_name = \
                os.path.join(os.path.dirname(package.filename), config_file_name)
            if not os.path.exists(full_config_file_name):
                raise RuntimeError(
                    f"Error rosdoc2 config file '{config_file_name}', "
                    f"from '{package.filename}', does not exist")
            with open(full_config_file_name, 'r') as f:
                # Replace default with user supplied config file.
                rosdoc_config_file = f.read()
            rosdoc_config_file_name = full_config_file_name

    # If not supplied by the user, use default.
    if rosdoc_config_file is None:
        package_map = create_format_map_from_package(package)
        rosdoc_config_file = DEFAULT_ROSDOC_CONFIG_FILE.format_map(package_map)
        rosdoc_config_file_name = '<default config>'

    # Parse config file
    build_context = BuildContext(
        configuration_file_path=rosdoc_config_file_name,
        package_object=package,
        tool_options=tool_options,
    )

    # Is this python under ament_cmake?
    for depends in package['buildtool_depends']:
        if str(depends) == 'ament_cmake_python':
            build_context.ament_cmake_python = True
    configs = list(yaml.load_all(rosdoc_config_file, Loader=yaml.SafeLoader))

    (settings_dict, builders_list) = parse_rosdoc2_yaml(configs, build_context)

    # Extend rosdoc2.yaml if desired
    #
    # An optional fie may be used to modify the values in rosdoc2.yaml for this package. The format
    # of this file is as follows:
    """
---
<some_identifier_describing_a_collection_of_packages>:
    packages:
        <1st package name>:
            <anything valid in rosdoc2.yaml file>
        <2nd package name>:
            <more valid rosdoc2.yaml>
<another_description>
    packages:
        <another_package_name>
            <valid rosdoc2.yaml>
    """
    yaml_extend = tool_options.yaml_extend
    if yaml_extend:
        if not os.path.isfile(yaml_extend):
            raise ValueError(
                f"yaml_extend path '{yaml_extend}' is not a file")
        with open(yaml_extend, 'r') as f:
            yaml_extend_text = f.read()
        extended_settings = yaml.load(yaml_extend_text, Loader=yaml.SafeLoader)
        for ex_name in extended_settings:
            if package.name in extended_settings[ex_name]['packages']:
                extended_object = extended_settings[ex_name]['packages'][package.name]
                if 'settings' in extended_object:
                    for key, value in extended_object['settings'].items():
                        settings_dict[key] = value
                        logger.info(f'Overriding rosdoc2.yaml setting  <{key}> with <{value}>')
                if 'builders' in extended_object:
                    for ex_builder in extended_object['builders']:
                        ex_builder_name = next(iter(ex_builder))
                        # find this object in the builders list
                        for user_builder in builders_list:
                            user_builder_name = next(iter(user_builder))
                            if user_builder_name == ex_builder_name:
                                for builder_k, builder_v in ex_builder[ex_builder_name].items():
                                    logger.info(f'Overriding rosdoc2 builder <{ex_builder_name}> '
                                                f'property <{builder_k}> with <{builder_v}>')
                                    user_builder[user_builder_name][builder_k] = builder_v

    # if None, python_source is set to either './<package.name>' or 'src/<package.name>'
    build_context.python_source = settings_dict.get('python_source', None)
    build_context.always_run_doxygen = settings_dict.get('always_run_doxygen', False)
    build_context.always_run_sphinx_apidoc = settings_dict.get('always_run_sphinx_apidoc', False)
    build_context.build_type = settings_dict.get('override_build_type', build_context.build_type)

    builders = []
    for builder in builders_list:
        builder_name = next(iter(builder))
        builders.append(create_builder_by_name(builder_name,
                                               builder_dict=builder[builder_name],
                                               build_context=build_context))

    return (settings_dict, builders)
