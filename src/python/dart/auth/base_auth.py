class BaseAuth():
    additional_auth_endpoints = None

    def handle_login_request(self):
        raise NotImplementedError

    def process_login_response(self):
        raise NotImplementedError

    def handle_logout_request(self):
        raise NotImplementedError
