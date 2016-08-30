import argparse
from dart.util.logging_utils import DartLogger

from dart.service.secrets import Secrets
from dart.tool.tool_runner import Tool

_logger = DartLogger(__name__)


class PutSecretTool(Tool):
    def __init__(self, key, content):
        super(PutSecretTool, self).__init__(_logger)
        self.key = key
        self.content = content

    def run(self):
        secrets = self.app_context.get(Secrets)
        assert isinstance(secrets, Secrets)
        secrets.put(self.key, self.content)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-k', '--key', action='store', dest='key', required=True)
    parser.add_argument('-c', '--content', action='store', dest='content', required=True)
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    PutSecretTool(args.key, args.content).run()
