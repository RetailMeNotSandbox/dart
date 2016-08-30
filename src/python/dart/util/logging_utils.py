import logging
from flask import g

class DartLogger(logging.getLoggerClass()):
    def __init__(self, logger_name):
        self._logger = logging.getLogger(logger_name)

    def req_id(self):
        if (g and g.get('request_id') is not None):
          return g.get('request_id', '')

        return ''

    def message(self, msg):
        return "*** %s %s" % (self.req_id(), msg)

    def info(self, msg, *args, **kwargs):
        self._logger.info(self.message(msg))

    def debug(self, msg, *args, **kwargs):
        self._logger.debug(self.message(msg))

    def warn(self, msg, *args, **kwargs):
        self._logger.warn(self.message(msg))

    def error(self, msg, *args, **kwargs):
        self._logger.error(self.message(msg))

    def fatal(self, msg, *args, **kwargs):
        self._logger.fatal(self.message(msg))