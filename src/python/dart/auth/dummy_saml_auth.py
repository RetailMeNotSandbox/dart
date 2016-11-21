from dart.auth.saml_auth import SamlAuth
from flask import redirect

class DummySamlAuth(SamlAuth):

    def __init__(self, request):
        self.request = request
        self.prepared_request = self._prepare_request()
        self.auth = self._init_saml_auth()

    def handle_login_request(self):
        #session['user_id'] = 'dart@client.rmn'
        return redirect('/')

    def handle_logout_request(self):
        return redirect('/')