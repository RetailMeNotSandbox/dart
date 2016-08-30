import argparse
from dart.util.logging_utils import DartLogger

from dart.service.secrets import Secrets
from dart.tool.tool_runner import Tool

_logger = DartLogger(__name__)


class DeleteSecretTool(Tool):
    def __init__(self, key):
        super(DeleteSecretTool, self).__init__(_logger)
        self.key = key

    def run(self):
        secrets = self.app_context.get(Secrets)
        assert isinstance(secrets, Secrets)
        secrets.delete(self.key)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-k', '--key', action='store', dest='key', required=True)
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    DeleteSecretTool(args.key).run()
