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

import yaml

from .builders import create_builder_by_name


def parse_rosdoc2_yaml(yaml_string, build_context):
    """
    Parse a rosdoc2.yaml configuration string, returning it as a tuple of settings and builders.

    :return: a tuple with the first item being the tool settings as a dictionary,
        and the second item being a list of Builder objects.
    """
    configs = list(yaml.load_all(yaml_string, Loader=yaml.SafeLoader))
    file_name = build_context.configuration_file_path
    if len(configs) != 2:
        raise ValueError(
            f"Error parsing file '{file_name}', "
            f"expected a YAML file with two sections, separated by '---', found {len(configs)}.")
    attic, config = configs
    if 'type' not in attic or attic['type'] != 'rosdoc2 config':
        raise ValueError(
            f"Error parsing file '{file_name}', "
            f"expected the first section of the YAML file to have a \"type: 'rosdoc2 config'\".")
    if 'version' not in attic or attic['version'] != 1:
        raise ValueError(
            f"Error parsing file '{file_name}', "
            f"expected the first section of the YAML file to have a 'version' entry, "
            'and only version 1 is supported.')
    if not isinstance(config, dict):
        raise ValueError(
            f"Error parsing file '{file_name}', in the second section, "
            f'expected something like dict{{settings: <tool settings>, builders: <builders>}}, '
            f"got a '{type(config)}' instead")

    if 'settings' not in config:
        raise ValueError(
            f"Error parsing file '{file_name}', in the second section, "
            f"expected a 'settings' key")
    settings_dict = config['settings']
    if not isinstance(settings_dict, dict):
        raise ValueError(
            f"Error parsing file '{file_name}', in the second section, value 'settings', "
            f'expected a dict{{output_dir: build_settings, ...}}, '
            f"got a '{type(settings_dict)}' instead")

    build_context.python_source = settings_dict.get('python_source', None)
    build_context.always_run_doxygen = settings_dict.get('always_run_doxygen', False)
    build_context.always_run_sphinx_apidoc = settings_dict.get('always_run_sphinx_apidoc', False)
    build_context.build_type = settings_dict.get('override_build_type', build_context.build_type)
    build_context.show_exec_dep = settings_dict.get('show_exec_dep', None)

    if 'builders' not in config:
        raise ValueError(
            f"Error parsing file '{file_name}', in the second section, "
            f"expected a 'builders' key")
    builders_list = config['builders']
    if not isinstance(builders_list, list):
        raise ValueError(
            f"Error parsing file '{file_name}', in the second section, value 'builders', "
            'expected a list of builders, '
            f"got a '{type(builders_list)}' instead")

    builders = []
    for builder in builders_list:
        if len(builder) != 1:
            raise ValueError(
                f"Error parsing file '{file_name}', in the second section, each builder "
                'must have exactly one key (which is the type of builder to use)')
        builder_name = next(iter(builder))
        builders.append(create_builder_by_name(builder_name,
                                               builder_dict=builder[builder_name],
                                               build_context=build_context))

    return (settings_dict, builders)
