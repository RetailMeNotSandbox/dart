class DartRequestException(Exception):
    def __init__(self, response, message=None):
        self.response = response
        super(Exception, self).__init__(message or (response.status_code, response.content))


class DartValidationException(Exception):
    pass


class DartConditionalUpdateFailedException(Exception):
    pass


class DartLockTimeoutException(Exception):
    pass


class DartActionException(Exception):
    def __init__(self, message, data=None):
        self.data = data
        super(Exception, self).__init__(message)


class DartAuthenticationException(Exception):
    def __init__(self, message, data=None):
        self.data = data
        super(Exception, self).__init__(message)


class DartUserError(Exception):
    pass
