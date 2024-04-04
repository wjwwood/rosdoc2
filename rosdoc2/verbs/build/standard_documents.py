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

import os
import shutil


standard_documents_rst = """\
Standard Documents
==================

.. toctree::
   :maxdepth: 1
   :glob:

   standard_docs/*
"""


def locate_standard_documents(package_xml_directory):
    """Locate standard documents."""
    names = ['readme', 'license', 'contributing', 'changelog', 'quality_declaration']
    found_paths = {}
    package_directory_items = os.scandir(package_xml_directory)
    for item in package_directory_items:
        if not item.is_file():
            continue
        (basename, ext) = os.path.splitext(item.name)
        for name in names:
            if name in found_paths:
                continue
            if basename.lower() == name:
                filetype = None
                if ext.lower() in ['.md', '.markdown']:
                    filetype = 'md'
                elif ext.lower() == '.rst':
                    filetype = 'rst'
                else:
                    filetype = 'other'
                found_paths[name] = {
                    'path': item.path,
                    'filename': item.name,
                    'type': filetype
                }
    return found_paths


def generate_standard_document_files(standard_docs, wrapped_sphinx_directory):
    """Generate rst documents to link to standard documents."""
    wrapped_sphinx_directory = os.path.abspath(wrapped_sphinx_directory)
    standards_sphinx_directory = os.path.join(wrapped_sphinx_directory, 'standard_docs')
    standards_original_directory = os.path.join(standards_sphinx_directory, 'original')
    if len(standard_docs):
        # Create the standards.rst document that will link to the actual documents
        os.makedirs(standards_sphinx_directory, exist_ok=True)
        os.makedirs(standards_original_directory, exist_ok=True)
        standard_documents_rst_path = os.path.join(
            wrapped_sphinx_directory, 'standards.rst')
        with open(standard_documents_rst_path, 'w+') as f:
            f.write(standard_documents_rst)

    for key, standard_doc in standard_docs.items():
        # Copy the original document to the sphinx project
        shutil.copy(standard_doc['path'], standards_original_directory)
        # generate the file according to type
        file_contents = f'{key.upper()}\n'
        # using ')' as a header marker to assure the name is the title
        file_contents += ')' * len(key) + '\n\n'
        file_type = standard_doc['type']
        file_path = f"original/{standard_doc['filename']}"
        if file_type == 'rst':
            file_contents += f'.. include:: {file_path}\n'
        elif file_type == 'md':
            file_contents += f'.. include:: {file_path}\n'
            file_contents += '   :parser: myst_parser.sphinx_\n'
        else:
            file_contents += f'.. literalinclude:: {file_path}\n'

        with open(os.path.join(standards_sphinx_directory, f'{key.upper()}.rst'), 'w+') as f:
            f.write(file_contents)
