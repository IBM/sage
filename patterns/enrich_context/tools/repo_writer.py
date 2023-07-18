import os


class Repo_Writer:
    def __init__(self, out_dir) -> None:
        self.out_dir = out_dir
        self._buffer = {}
        self.max_buffer = 100

    def _get_lines(self, src_type, repo_name, init=False):
        if src_type is None or repo_name is None:
            return None

        v1 = None
        if src_type not in self._buffer:
            if init:
                v1 = {}
                self._buffer[src_type] = v1
            else:
                return None
        else:
            v1 = self._buffer[src_type]

        v2 = None
        if repo_name not in v1:
            if init:
                v2 = []
                v1[repo_name] = v2
            else:
                return None
        else:
            v2 = v1[repo_name]

        return v2

    def save_to_buffer(self, src_type=None, repo_name=None, str=None):
        if src_type is None or repo_name is None or str is None:
            return

        lines = self._get_lines(src_type, repo_name, init=True)
        lines.append(str)

        if len(lines) > self.max_buffer:
            self._dump_buffer(src_type, repo_name)

    def _dump_buffer(self, src_type, repo_name):
        os.makedirs(os.path.join(self.out_dir, src_type, repo_name), exist_ok=True)
        file = os.path.join(self.out_dir, src_type, repo_name, "org-ftdata.json")
        lines = self._get_lines(src_type, repo_name)
        with open(file, mode="a") as f:
            for line in lines:
                f.write(f"{line.rstrip()}\n")
        self._buffer[src_type][repo_name] = []

    def save_all(self):
        for src_type in self._buffer:
            for repo_name in self._buffer[src_type]:
                self._dump_buffer(src_type, repo_name)

    def get_repo_names(self, src_type):
        return self._buffer[src_type].keys()
