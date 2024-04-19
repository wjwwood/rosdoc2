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

from importlib import resources
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess

from jinja2 import Template
import setuptools
from sphinx.cmd.build import main as sphinx_main

from ..builder import Builder
from ..collect_inventory_files import collect_inventory_files
from ..create_format_map_from_package import create_format_map_from_package
from ..generate_interface_docs import generate_interface_docs
from ..include_user_docs import include_user_docs
from ..standard_documents import generate_standard_document_files, locate_standard_documents

logger = logging.getLogger('rosdoc2')


def esc_backslash(path):
    """Escape backslashes to support Windows paths in strings."""
    return path.replace('\\', '\\\\') if path else path


rosdoc2_wrapping_conf_py_template = """\
## Generated by rosdoc2.verbs.build.builders.SphinxBuilder.
## This conf.py imports the user defined (or default if none was provided)
## conf.py, extends the settings to support Breathe and Exhale and to set up
## intersphinx mappings correctly, among other things.

import os
import sys

## exec the user's conf.py to bring all of their settings into this file.
exec(open("{user_conf_py_filename}").read())

def ensure_global(name, default):
    if name not in globals():
        globals()[name] = default

## Based on the rosdoc2 settings, do various things to the settings before
## letting Sphinx continue.

ensure_global('rosdoc2_settings', {{}})
ensure_global('extensions', [])
ensure_global('project', "{package_name}")
ensure_global('author', \"\"\"{package_authors}\"\"\")
ensure_global('release', "{package.version}")
ensure_global('version', "{package_version_short}")

if rosdoc2_settings.get('enable_autodoc', True):
    print('[rosdoc2] enabling autodoc', file=sys.stderr)
    extensions.append('sphinx.ext.autodoc')

    pkgs_to_mock = []
    import importlib
    for exec_depend in {exec_depends}:
        try:
            # Some python dependencies may be dist packages.
            exec_depend = exec_depend.split("python3-")[-1]
            importlib.import_module(exec_depend)
        except ImportError:
            pkgs_to_mock.append(exec_depend)
    # todo(YV): If users provide autodoc_mock_imports in their conf.py
    # it will be overwritten by those in exec_depends.
    # Consider appending to autodoc_mock_imports instead.
    autodoc_mock_imports = pkgs_to_mock

if rosdoc2_settings.get('enable_intersphinx', True):
    print('[rosdoc2] enabling intersphinx', file=sys.stderr)
    extensions.append('sphinx.ext.intersphinx')

build_type = '{build_type}'
always_run_doxygen = {always_run_doxygen}
# By default, the `exhale`/`breathe` extensions should be added if `doxygen` was invoked
is_doxygen_invoked = {did_run_doxygen}

if rosdoc2_settings.get('enable_breathe', is_doxygen_invoked):
    # Configure Breathe.
    # Breathe ingests the XML output from Doxygen and makes it accessible from Sphinx.
    print('[rosdoc2] enabling breathe', file=sys.stderr)
    # First check that doxygen would have been run
    if not is_doxygen_invoked:
        raise RuntimeError(
            "Cannot enable the 'breathe' extension if 'doxygen' is not invoked. "
            "Please enable 'always_run_doxygen' if the package is not an "
            "'ament_cmake' or 'cmake' package.")
    ensure_global('breathe_projects', {{}})
    breathe_projects.update({{{breathe_projects}}})
    if breathe_projects:
        # Enable Breathe and arbitrarily select the first project.
        extensions.append('breathe')
        breathe_default_project = next(iter(breathe_projects.keys()))

if rosdoc2_settings.get('enable_exhale', is_doxygen_invoked):
    # Configure Exhale.
    # Exhale uses the output of Doxygen and Breathe to create easier to browse pages
    # for classes and functions documented with Doxygen.
    # This is similar to the class hierarchies and namespace listing provided by
    # Doxygen out of the box.
    print('[rosdoc2] enabling exhale', file=sys.stderr)
    # First check that doxygen would have been run
    if not is_doxygen_invoked:
        raise RuntimeError(
            "Cannot enable the 'breathe' extension if 'doxygen' is not invoked. "
            "Please enable 'always_run_doxygen' if the package is not an "
            "'ament_cmake' or 'cmake' package.")
    extensions.append('exhale')
    ensure_global('exhale_args', {{}})

    default_exhale_specs_mapping = {{
        'page': [':content-only:'],
        **dict.fromkeys(
            ['class', 'struct'],
            [':members:', ':protected-members:', ':undoc-members:']),
    }}

    exhale_specs_mapping = rosdoc2_settings.get(
        'exhale_specs_mapping', default_exhale_specs_mapping)

    from exhale import utils
    exhale_args.update({{
        # These arguments are required.
        "containmentFolder": "{wrapped_sphinx_directory}/generated",
        "rootFileName": "index.rst",
        "rootFileTitle": "C++ API",
        "doxygenStripFromPath": "..",
        # Suggested optional arguments.
        "createTreeView": True,
        "fullToctreeMaxDepth": 1,
        "unabridgedOrphanKinds": [],
        "fullApiSubSectionTitle": "Full C++ API",
        # TIP: if using the sphinx-bootstrap-theme, you need
        # "treeViewIsBootstrap": True,
        "exhaleExecutesDoxygen": False,
        # Maps markdown files to the "md" lexer, and not the "markdown" lexer
        # Pygments registers "md" as a valid markdown lexer, and not "markdown"
        "lexerMapping": {{r".*\\.(md|markdown)$": "md",}},
        "customSpecificationsMapping": utils.makeCustomSpecificationsMapping(
            lambda kind: exhale_specs_mapping.get(kind, [])),
    }})

if rosdoc2_settings.get('override_theme', True):
    extensions.append('sphinx_rtd_theme')
    html_theme = 'sphinx_rtd_theme'
    print(f"[rosdoc2] overriding theme to be '{{html_theme}}'", file=sys.stderr)

if rosdoc2_settings.get('automatically_extend_intersphinx_mapping', True):
    print(f"[rosdoc2] extending intersphinx mapping", file=sys.stderr)
    if 'sphinx.ext.intersphinx' not in extensions:
        raise RuntimeError(
            "Cannot extend intersphinx mapping if 'sphinx.ext.intersphinx' "
            "has not been added to the extensions")
    ensure_global('intersphinx_mapping', {{
        {intersphinx_mapping_extensions}
    }})

if rosdoc2_settings.get('support_markdown', True):
    print(f"[rosdoc2] adding markdown parser", file=sys.stderr)
    # The `myst_parser` is used specifically if there are markdown files
    # in the sphinx project
    extensions.append('myst_parser')
"""  # noqa: W605

default_conf_py_template = """\
## Generated by rosdoc2.verbs.build.builders.SphinxBuilder.
## Based on a recent output from Sphinx-quickstart.

# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join('{python_src_directory}', '..')))


# -- Project information -----------------------------------------------------

project = '{package.name}'
# TODO(tfoote) The docs say year and author but we have this and it seems more relevant.
copyright = 'The <{package.name}> Contributors. License: {package_licenses}'
author = \"\"\"{package_authors}\"\"\"

# The full version, including alpha/beta/rc tags
release = '{package.version}'

version = '{package_version_short}'


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
## rosdoc2 will extend the extensions to enable Breathe and Exhale if you
## do not add them here, as well as others, perhaps.
## If you add them manually rosdoc2 may still try to configure them.
## See the rosdoc2_settings below for some options on avoiding that.
extensions = [
    'sphinx_rtd_theme',
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []

master_doc = 'index'

source_suffix = {{
    '.rst': 'restructuredtext',
    '.md': 'markdown',
    '.markdown': 'markdown',
}}

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
## rosdoc2 will override the theme, but you may set one here for running Sphinx
## without the rosdoc2 tool.
html_theme = 'sphinx_rtd_theme'

html_theme_options = {{
    # Toc options
    'collapse_navigation': False,
    'sticky_navigation': True,
    'navigation_depth': 4,
    'includehidden': True,
    'titles_only': False,
}}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
## rosdoc2 comments this out by default because we're not creating it.
# html_static_path = ['_static']

# -- Options for rosdoc2 -----------------------------------------------------

## These settings are specific to rosdoc2, and if Sphinx is run without rosdoc2
## they will be safely ignored.
## None are required by default, so the lines below show the default values,
## therefore you will need to uncomment the lines and change their value
## if you want change the behavior of rosdoc2.
rosdoc2_settings = {{
    ## This setting, if True, will ensure breathe is part of the 'extensions',
    ## and will set all of the breathe configurations, if not set, and override
    ## settings as needed if they are set by this configuration.
    # 'enable_breathe': True,

    ## This setting, if True, will ensure exhale is part of the 'extensions',
    ## and will set all of the exhale configurations, if not set, and override
    ## settings as needed if they are set by this configuration.
    # 'enable_exhale': True,

    ## This setting, if provided, allows option specification for breathe
    ## directives through exhale. If not set, exhale defaults will be used.
    ## If an empty dictionary is provided, breathe defaults will be used.
    # 'exhale_specs_mapping': {{}},

    ## This setting, if True, will ensure autodoc is part of the 'extensions'.
    # 'enable_autodoc': True,

    ## This setting, if True, will ensure intersphinx is part of the 'extensions'.
    # 'enable_intersphinx': True,

    ## This setting, if True, will have the 'html_theme' overridden to provide
    ## a consistent style across all of the ROS documentation.
    # 'override_theme': True,

    ## This setting, if True, will automatically extend the intersphinx mapping
    ## using inventory files found in the cross-reference directory.
    ## If false, the `found_intersphinx_mappings` variable will be in the global
    ## scope when run with rosdoc2, and could be conditionally used in your own
    ## Sphinx conf.py file.
    # 'automatically_extend_intersphinx_mapping': True,

    ## Support markdown
    # 'support_markdown': True,
}}
"""


class SphinxBuilder(Builder):
    """
    Builder for Sphinx.

    Supported keys for the builder_entry_dictionary include:

    - name (str) (required)
      - name of the documentation, used in reference to the content generated by this builder
    - builder (str) (required)
      - required for all builders, must be 'sphinx' to use this class
    - sphinx_sourcedir (str) (optional)
      - directory containing the Sphinx project, i.e. the `conf.py`, the setting
        you would pass to sphinx-build as SOURCEDIR. Defaults to `doc`.
    """

    def __init__(self, builder_name, builder_entry_dictionary, build_context):
        """Construct a new SphinxBuilder."""
        super(SphinxBuilder, self).__init__(
            builder_name,
            builder_entry_dictionary,
            build_context)

        assert self.builder_type == 'sphinx'

        self.sphinx_sourcedir = None
        self.doxygen_xml_directory = None
        configuration_file_path = build_context.configuration_file_path
        if not os.path.exists(configuration_file_path):
            # This can be the case if the default config is used from a string.
            # Use package.xml instead.
            configuration_file_path = self.build_context.package.filename
        configuration_file_dir = os.path.abspath(os.path.dirname(configuration_file_path))

        # Process keys.
        for key, value in builder_entry_dictionary.items():
            if key in ['name', 'output_dir']:
                continue
            if key == 'sphinx_sourcedir':
                sphinx_sourcedir = os.path.join(configuration_file_dir, value)
                if not os.path.isdir(sphinx_sourcedir):
                    raise RuntimeError(
                        f"Error Sphinx SOURCEDIR '{value}' does not exist relative "
                        f"to '{configuration_file_path}', or is not a directory.")
                self.sphinx_sourcedir = sphinx_sourcedir
            elif key == 'doxygen_xml_directory':
                self.doxygen_xml_directory = value
                # Must check for the existence of this later, as it may not have been made yet.
            else:
                raise RuntimeError(f"Error the Sphinx builder does not support key '{key}'")

        # Prepare the template variables for formatting strings.
        self.template_variables = create_format_map_from_package(build_context.package)

    def build(self, *, doc_build_folder, output_staging_directory):
        """Actually do the build."""
        # Check that doxygen_xml_directory exists relative to output staging, if specified.
        if self.doxygen_xml_directory is not None:
            self.doxygen_xml_directory = \
                os.path.join(output_staging_directory, self.doxygen_xml_directory)
            self.doxygen_xml_directory = os.path.abspath(self.doxygen_xml_directory)

            if not os.path.isdir(self.doxygen_xml_directory):
                self.doxygen_xml_directory = None
                logger.info('No doxygen_xml_directory found, apparently doxygen did not run')
                if self.build_context.always_run_doxygen:
                    raise RuntimeError(
                        f"Error the 'doxygen_xml_directory' specified "
                        f"'{self.doxygen_xml_directory}' does not exist.")

        package_xml_directory = os.path.dirname(self.build_context.package.filename)
        # If 'python_source' is specified, construct 'python_src_directory' from it
        if self.build_context.python_source is not None:
            python_src_directory = \
                os.path.abspath(
                    os.path.join(
                        package_xml_directory,
                        self.build_context.python_source))
        # If not provided, try to find the python source directory
        else:
            package_list = setuptools.find_packages(where=package_xml_directory)
            if self.build_context.package.name in package_list:
                python_src_directory = \
                    os.path.abspath(
                        os.path.join(
                            package_xml_directory,
                            self.build_context.package.name))
            else:
                python_src_directory = None

        # We will ultimately run the sphinx project from a wrapped directory. Create it now,
        # so that we can put generated items there.
        wrapped_sphinx_directory = os.path.abspath(
            os.path.join(doc_build_folder, 'wrapped_sphinx_directory'))
        os.makedirs(wrapped_sphinx_directory, exist_ok=True)

        # Generate rst documents for interfaces
        interface_counts = generate_interface_docs(
            package_xml_directory,
            self.build_context.package.name,
            os.path.join(wrapped_sphinx_directory, 'interfaces')
        )
        logger.info(f'interface_counts: {interface_counts}')

        # locate standard documents
        standard_docs = locate_standard_documents(package_xml_directory)
        if standard_docs:
            generate_standard_document_files(standard_docs, wrapped_sphinx_directory)
        logger.info(f'standard_docs: {standard_docs}')

        # include user documentation
        doc_directories = include_user_docs(package_xml_directory, wrapped_sphinx_directory)
        logger.info(f'doc_directories: {doc_directories}')

        # Check if the user provided a sphinx directory.
        sphinx_project_directory = self.sphinx_sourcedir
        if sphinx_project_directory is not None:
            # We do not need to check if this directory exists, as that was done in __init__.
            logger.info(
                'Note: the user provided sourcedir for Sphinx '
                f"'{sphinx_project_directory}' will be used.")
        else:
            # If the user does not supply a Sphinx sourcedir, check the standard locations.
            standard_sphinx_sourcedir = self.locate_sphinx_sourcedir_from_standard_locations()
            if standard_sphinx_sourcedir is not None:
                logger.info(
                    'Note: no sourcedir provided, but a Sphinx sourcedir located in the '
                    f"standard location '{standard_sphinx_sourcedir}' and that will be used.")
                sphinx_project_directory = standard_sphinx_sourcedir
            else:
                # If the user does not supply a Sphinx sourcedir, and there is no Sphinx project
                # in the conventional location, i.e. '<package dir>/doc', create a temporary
                # Sphinx project in the doc build directory to enable cross-references.
                logger.info(
                    'Note: no sourcedir provided by the user and no Sphinx sourcedir was found '
                    'in the standard locations, therefore using a default Sphinx configuration.')
                sphinx_project_directory = os.path.join(doc_build_folder, 'default_sphinx_project')

                self.generate_default_project_into_directory(
                    sphinx_project_directory, python_src_directory)

        # Collect intersphinx mapping extensions from discovered inventory files.
        inventory_files = \
            collect_inventory_files(self.build_context.tool_options.cross_reference_directory)
        base_url = self.build_context.tool_options.base_url
        intersphinx_mapping_extensions = [
            f"'{package_name}': "
            f"('{base_url}/{package_name}/{inventory_dict['location_data']['relative_root']}', "
            f"'{esc_backslash(os.path.abspath(inventory_dict['inventory_file']))}')"
            for package_name, inventory_dict in inventory_files.items()
            # Exclude ourselves.
            if package_name != self.build_context.package.name
        ]

        build_context = self.build_context
        has_python = build_context.build_type == 'ament_python' or \
            build_context.always_run_sphinx_apidoc or \
            build_context.ament_cmake_python

        always_run_doxygen = build_context.always_run_doxygen
        has_cpp = build_context.build_type in ['ament_cmake', 'cmake'] or always_run_doxygen
        package = self.build_context.package

        # Detect meta packages. They have no build_dependencies, do have exec_dependencies,
        # and have no subdirectories except for possibly 'doc'.
        is_meta = True
        if package.build_depends or not package.exec_depends:
            is_meta = False
        else:
            pp = Path(package_xml_directory)
            subdirectories = [x for x in pp.iterdir() if x.is_dir()]
            for subdirectory in subdirectories:
                if subdirectory.name != 'doc':
                    is_meta = False
                    continue

        self.template_variables.update({
            'has_python': has_python,
            'has_cpp': has_cpp,
            'has_standard_docs': bool(standard_docs),
            'has_documentation': bool(doc_directories),
            'has_readme': 'readme' in standard_docs,
            'interface_counts': interface_counts,
            'package': package,
            'base_url': base_url,
            'is_meta': is_meta or package.is_metapackage(),
        })

        # Setup rosdoc2 Sphinx file which will include and extend the one in
        # `sphinx_project_directory`.
        self.generate_wrapping_rosdoc2_sphinx_project_into_directory(
            wrapped_sphinx_directory,
            sphinx_project_directory,
            python_src_directory,
            intersphinx_mapping_extensions)

        # If the package has python code, then invoke `sphinx-apidoc` before building
        if has_python:
            if not python_src_directory or not os.path.isdir(python_src_directory):
                raise RuntimeError(
                    'Could not locate source directory to invoke sphinx-apidoc in. '
                    'If this is package does not have a standard Python package layout, '
                    "please specify the Python source in 'rosdoc2.yaml'.")
            cmd = [
                'sphinx-apidoc',
                '-o', wrapped_sphinx_directory,
                '-e',  # Document each module in its own page.
                python_src_directory,
            ]
            logger.info(
                f"Running sphinx-apidoc: '{' '.join(cmd)}' in '{wrapped_sphinx_directory}'"
            )
            completed_process = subprocess.run(cmd, cwd=wrapped_sphinx_directory)
            msg = f"sphinx-apidoc exited with return code '{completed_process.returncode}'"
            if completed_process.returncode == 0:
                logger.debug(msg)
            else:
                raise RuntimeError(msg)

        # Invoke Sphinx-build.
        sphinx_output_dir = os.path.abspath(
            os.path.join(wrapped_sphinx_directory, 'sphinx_output'))
        logger.info(
            f"Running sphinx_build with: [{wrapped_sphinx_directory}, '{sphinx_output_dir}]'"
        )
        returncode = sphinx_main([wrapped_sphinx_directory, sphinx_output_dir])
        msg = f"sphinx_build exited with return code '{returncode}'"
        if returncode == 0:
            logger.info(msg)
        else:
            raise RuntimeError(msg)

        # Copy the inventory file into the cross-reference directory, but also leave the output.
        inventory_file_name = os.path.join(sphinx_output_dir, 'objects.inv')
        destination = os.path.join(
            self.build_context.tool_options.cross_reference_directory,
            self.build_context.package.name,
            os.path.basename(inventory_file_name))
        logger.info(
            f"Moving inventory file '{inventory_file_name}' into "
            f"cross-reference directory '{destination}'")
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy(
            os.path.abspath(inventory_file_name),
            os.path.abspath(destination)
        )

        # Create a .location.json file as well, so we can know the relative path to the root
        # of the sphinx content from the package's documentation root.
        data = {
            'relative_root': self.output_dir,
        }
        with open(os.path.abspath(destination) + '.location.json', 'w+') as f:
            f.write(json.dumps(data))
        # Put it with the Sphinx generated content as well.
        with open(os.path.abspath(inventory_file_name) + '.location.json', 'w+') as f:
            f.write(json.dumps(data))

        # Return the directory into which Sphinx generated.
        return sphinx_output_dir

    def locate_sphinx_sourcedir_from_standard_locations(self):
        """
        Return the location of a Sphinx project for the package.

        If the sphinx configuration exists in a standard location, return it,
        otherwise return None.  The standard locations are
        '<package.xml directory>/doc/source/conf.py' and
        '<package.xml directory>/doc/conf.py', for projects that selected
        "separate source and build directories" when running Sphinx-quickstart and
        those that did not, respectively.
        """
        package_xml_directory = os.path.dirname(self.build_context.package.filename)
        options = [
            os.path.join(package_xml_directory, 'doc'),
            os.path.join(package_xml_directory, 'doc', 'source'),
        ]
        for option in options:
            if os.path.isfile(os.path.join(option, 'conf.py')):
                return option
        return None

    def generate_default_project_into_directory(
            self, sphinx_project_directory, python_src_directory):
        """Generate the default project configuration files."""
        os.makedirs(sphinx_project_directory, exist_ok=True)

        package = self.build_context.package
        self.template_variables.update({
            'package': package,
            'python_src_directory': esc_backslash(python_src_directory),
            'package_version_short': '.'.join(package.version.split('.')[0:2]),
            'package_licenses': ', '.join(package.licenses),
            'package_authors': ', '.join(set(
                [a.name for a in package.authors] + [m.name for m in package.maintainers]
            )),
        })

        with open(os.path.join(sphinx_project_directory, 'conf.py'), 'w+') as f:
            f.write(default_conf_py_template.format_map(self.template_variables))

    def generate_wrapping_rosdoc2_sphinx_project_into_directory(
        self,
        wrapped_sphinx_directory,
        sphinx_project_directory,
        python_src_directory,
        intersphinx_mapping_extensions,
    ):
        """Generate the rosdoc2 sphinx project configuration files."""
        # Generate a default index.rst
        package = self.build_context.package
        logger.info('Using a default index.rst.jinja')
        template_path = resources.files('rosdoc2.verbs.build.builders').joinpath('index.rst.jinja')
        template_jinja = template_path.read_text()

        index_rst = Template(template_jinja).render(self.template_variables)

        with open(os.path.join(wrapped_sphinx_directory, 'index.rst'), 'w+') as f:
            f.write(index_rst)

        # Copy all user content, like images or documentation files, and
        # source files to the wrapping directory
        #
        # If the user created an index.rst, it will overwrite our default here. Later we will
        # overwrite any user's conf.py with a wrapped version, that also includes any user's
        # conf.py variables.
        if sphinx_project_directory:
            try:
                shutil.copytree(
                    os.path.abspath(sphinx_project_directory),
                    os.path.abspath(wrapped_sphinx_directory),
                    dirs_exist_ok=True)

            except OSError as e:
                print(f'Failed to copy user content: {e}')

        package = self.build_context.package
        breathe_projects = []
        if self.doxygen_xml_directory is not None:
            breathe_projects.append(
                f'        "{package.name} Doxygen Project": '
                f'"{esc_backslash(self.doxygen_xml_directory)}"')
        self.template_variables.update({
            'python_src_directory': python_src_directory,
            'exec_depends': [exec_depend.name for exec_depend in package.exec_depends]
            + [doc_depend.name for doc_depend in package.doc_depends],
            'build_type': self.build_context.build_type,
            'always_run_doxygen': self.build_context.always_run_doxygen,
            'did_run_doxygen': self.doxygen_xml_directory is not None,
            'wrapped_sphinx_directory': esc_backslash(os.path.abspath(wrapped_sphinx_directory)),
            'user_conf_py_filename': esc_backslash(
                os.path.abspath(os.path.join(sphinx_project_directory, 'conf.py'))),
            'breathe_projects': ',\n'.join(breathe_projects) + '\n    ',
            'intersphinx_mapping_extensions': ',\n        '.join(intersphinx_mapping_extensions),
            'package': package,
            'package_authors': ', '.join(sorted(set(
                [a.name for a in package.authors] + [m.name for m in package.maintainers]
            ))),
            'package_version_short': '.'.join(package.version.split('.')[0:2]),
        })

        with open(os.path.join(wrapped_sphinx_directory, 'conf.py'), 'w+') as f:
            f.write(rosdoc2_wrapping_conf_py_template.format_map(self.template_variables))
