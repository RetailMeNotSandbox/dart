from flask import Blueprint, request, current_app, redirect, flash, url_for, render_template, g
from flask.ext.login import LoginManager, login_user, logout_user
from datetime import datetime

from dart.service.user import UserService
from dart.service.api_key import ApiKeyService
from dart.model.exception import DartAuthenticationException
from dart.auth.AuthenticationAlgoFactory import basic_auth

auth_bp = Blueprint('auth', __name__)

login_manager = LoginManager()

@auth_bp.route('/login', methods=['GET'])
@login_manager.unauthorized_handler
def get_login():
    auth = current_app.auth_class(request)
    ret =  auth.handle_login_request()
    return ret

@auth_bp.route('/login', methods=['POST'])
def post_login():
    auth = current_app.auth_class(request)
    user = auth.process_login_response()
    if user.is_authenticated:
        login_user(user)
        return redirect(request.args.get('next') or '/')
    flash('Login incorrect')
    return redirect(url_for('auth.get_login'))

@auth_bp.route('/logout', methods=['GET'])
def logout():
    auth = current_app.auth_class(request)
    ret = auth.handle_logout_request() # will logout from onelogin and call /auth/logout2
    logout_user()
    flash('logged out')
    return ret

# This is a redirect call from onelogin ('Single Logout URL' in app configuration).
@auth_bp.route('/logout2', methods=['GET'])
def logout2():
    return render_template('info.html')

@login_manager.user_loader
def load_user(user_id):
    user_service = current_app.dart_context.get(UserService)
    user = user_service.get_user(user_id, False)
    user.is_authenticated = (user.is_authenticated and user.session_expiration > datetime.utcnow())
    return user

@login_manager.request_loader
def api_auth(request):
    auth_header = request.headers.get('Authorization')
    if not (auth_header):
        # if the auth header is missing then it is assumed the API call is coming from the UI
        # and the request should load the user from the session cookie.
        return None

    auth_algo_name = auth_header.split(' ')[0]
    api_key_service = current_app.dart_context.get(ApiKeyService)
    user_service = current_app.dart_context.get(UserService)

    assert api_key_service
    assert user_service

    if (auth_algo_name == 'Basic'):
        return basic_auth(auth_header, api_key_service, user_service)
    elif (auth_algo_name == 'DART1_HMAC_SHA256'):
        pass


    # We did not match any auth algorithm if we reached here.
    raise DartAuthenticationException('DART is unable to authenticate your request')