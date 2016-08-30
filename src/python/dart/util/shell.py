import json
from dart.util.logging_utils import DartLogger
import os
import subprocess


_logger = DartLogger(__name__)


def call(cmd):
    _logger.info('\n' + cmd + '\n')
    try:
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True, env=os.environ.copy())
        _logger.info('\n' + result + '\n')
        return result
    except subprocess.CalledProcessError as e:
        _logger.error('This command "%s" produced this error: %s' % (cmd, json.dumps(e.output)))
        raise e
