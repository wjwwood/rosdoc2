# Copyright 2024 Open Source Robotics Foundation, Inc.
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
import shutil

from rosdoc2.slugify import slugify

logger = logging.getLogger('rosdoc2')

documentation_rst_template = """\
Documentation
=============

.. toctree::
   :maxdepth: 1
   :glob:

   {sphinx_project_directory}/*
"""

subdirectory_rst_template = """\
{name}/
{name_underline}=

.. toctree::
   :caption: Documentation in this subdirectory
   :maxdepth: 2
   :glob:

   {sphinx_project_directory}/{name}/*
"""


def include_user_docs(sphinx_project_directory: str,
                      output_dir: str,
                      package_xml_directory: str
                      ):
    """Generate rst files for user documents."""
    logger.info(f'include_user_docs: sphinx_project_directory <{sphinx_project_directory}> '
                f'output_dir <{output_dir}>')
    user_doc_directory = os.path.join(
        os.path.join(package_xml_directory, sphinx_project_directory))
    doc_directories = []
    for root, _, files in os.walk(user_doc_directory):
        for file in files:
            # ensure a valid documentation file exists, directories might only contain resources.
            (_, ext) = os.path.splitext(file)
            if ext in ['.rst', '.md', '.markdown']:
                logger.debug(f'Found renderable documentation file in {root} named {file}')
                doc_directories.append(os.path.relpath(root, user_doc_directory))
                break

    if not doc_directories:
        logger.debug(f'no documentation found in {user_doc_directory}')
        return doc_directories

    logger.info(f'Documentation found in directories {doc_directories}')
    # At this point we know that there are some directories that have documentation in them under
    # /doc, but we do not know which ones might also be needed for images or includes. So we copy
    # everything to the output directory.
    logger.info(f'Copying {os.path.join(package_xml_directory, sphinx_project_directory)} to '
                f'{os.path.join(output_dir, sphinx_project_directory)}')
    shutil.copytree(
        os.path.join(package_xml_directory, sphinx_project_directory),
        os.path.join(output_dir, sphinx_project_directory),
        dirs_exist_ok=True)

    toc_content = documentation_rst_template.format_map(
        {'sphinx_project_directory': sphinx_project_directory})
    # generate a glob rst entry for each directory with documents
    for relpath in doc_directories:
        # directories that will be explicitly listed in index.rst
        if relpath == '.':
            continue
        docname = 'user_docs_' + slugify(relpath)  # This is the name that sphinx uses
        content = subdirectory_rst_template.format_map(
            {'name': relpath,
             'name_underline': '=' * len(relpath),
             'sphinx_project_directory': sphinx_project_directory})
        sub_path = os.path.join(output_dir, docname + '.rst')
        with open(sub_path, 'w+') as f:
            f.write(content)
        toc_content += f'   {relpath}/ <{docname}>\n'

    sub_path = os.path.join(output_dir, 'user_docs.rst')
    with open(sub_path, 'w+') as f:
        f.write(toc_content)

    return doc_directories
