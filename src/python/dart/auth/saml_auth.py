# from dart.model.user import User
from dart.service.user import UserService
from dart.auth.base_auth import BaseAuth
from dart.model.user import User
from flask import current_app, make_response, Blueprint, redirect, session

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from urlparse import urlparse
from datetime import datetime


class SamlAuth(BaseAuth):
    additional_endpoints = Blueprint('saml_auth', __name__)

    def __init__(self, request):
        self.request = request
        self.prepared_request = self._prepare_request()
        self.auth = self._init_saml_auth()

    def _prepare_request(self):
        # If server is behind proxys or balancers use the HTTP_X_FORWARDED fields
        url_data = urlparse(self.request.url)
        return {
            'https': 'on' if self.request.scheme == 'https' else 'off',
            'http_host': self.request.host,
            'server_port': url_data.port,
            'script_name': self.request.path,
            'get_data': self.request.args.copy(),
            'post_data': self.request.form.copy(),
            'query_string': self.request.query_string
        }

    def _init_saml_auth(self):
        auth = OneLogin_Saml2_Auth(self.prepared_request, custom_base_path=current_app.config['auth']['config_path'])
        return auth

    def handle_login_request(self):
        return redirect(self.auth.login())

    def process_login_response(self):
        self.auth.process_response()
        ua = self.auth.get_attributes()
        USER_EMAIL = ua['User.email'][0]
        #session['user_id'] = USER_EMAIL

        user_service = current_app.dart_context.get(UserService)
        session_expiration = datetime.fromtimestamp(self.auth.get_session_expiration())
        user = User(USER_EMAIL, USER_EMAIL, USER_EMAIL, USER_EMAIL, True, session_expiration)
        user = user_service.login_user(user, self.auth.is_authenticated(), session_expiration)
        return user

    def handle_logout_request(self):
        return redirect(self.auth.logout())


@SamlAuth.additional_endpoints.route('/metadata', methods=['GET'])
def saml_metadata():
    auth = SamlAuth(request)
    settings = auth.auth.get_settings()
    metadata = settings.get_sp_metadata()
    errors = settings.validate_metadata(metadata)

    if len(errors) == 0:
        resp = make_response(metadata, 200)
        resp.headers['Content-Type'] = 'text/xml'
    else:
        resp = make_response(errors.join(', '), 500)
    return resp
