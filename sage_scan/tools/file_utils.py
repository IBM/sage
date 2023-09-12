# -*- mode:python; coding:utf-8 -*-

# Copyright (c) 2023 IBM Corp. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import tarfile
import json

# list target file names from tar.gz
def get_target_files_from_gzip(tar_gz_file, target_filename):
    files = []
    with tarfile.open(tar_gz_file, 'r:gz') as tar:
        for member in tar.getmembers():
            if member.name.endswith(target_filename):
                files.append(member.name)
    return files


# load target file content from tar.gz
def load_file_contents(member, tar_file:tarfile.TarFile):
    loaded_contents = []
    # read file in binary mode
    file_contents = tar_file.extractfile(member).readlines()
    for file_content in file_contents:
        file_content_str = file_content.decode('utf-8')
        try:
            content_dict = json.loads(file_content_str)
            loaded_contents.append(content_dict)
        except json.JSONDecodeError as e:
            print(f"JSONDecodeError: {e}")  
    return loaded_contents