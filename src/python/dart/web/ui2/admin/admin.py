import os
import logging
from flask import Blueprint, request
from flask.ext.jsontools import jsonapi
from flask.ext.login import login_required
from dart.auth.required_roles import required_roles
from sqlalchemy import text

from dart.context.database import db
from dart.model.mutex import Mutexes, MutexState
from dart.util.rand import random_id
from dart.config.config import configuration

from dart.web.ui.admin.admin_query import populate_dart_client_user, populate_dart_client_apikeys, clear_roles_table,\
    populate_roles_table, populate_user_roles_table, getPermissionServiceRolesAndIds

admin_bp = Blueprint('admin', __name__)

CONFIG_PATH = os.environ['DART_CONFIG']
CONFIG = configuration(CONFIG_PATH)
AUTH_CONFIG = CONFIG['auth']
DART_CLIENT_NAME = CONFIG['authorization']['dart_client_name']
PERMISSION_CONFIG = CONFIG['permission_service']

_logger = logging.getLogger(__name__)


def populate_user_api_secret_keys():
    ''' Under auth.predefined_auth_services we keep a triplet <user,api_key, secretKey>
        that an external service (e.g. portico, decode, savor) uses.  By being placed in a
        config file we can have different keys for different envs thaqt are always loaded when DART starts.
    '''
    if AUTH_CONFIG.get('predefined_auth_services'):
        for usr_api_secret in AUTH_CONFIG.get('predefined_auth_services'):
            items = usr_api_secret.split(" ")
            if len(items) == 3:
                print items
                populate_dart_client_user(items[0])
                populate_dart_client_apikeys(items[1], items[2], items[0])
            else:
                raise Exception("Predefined service user and api/secret keys must all exist. %s " % items)


@admin_bp.route('/create_all', methods=['POST'])
def create_all():
    db.create_all()

    for mutex in Mutexes.all():
        sql = """
            INSERT INTO mutex (id, version_id, created, updated, name, state)
            SELECT :id, 0, NOW(), NOW(), :name, :state
            WHERE NOT EXISTS (SELECT NULL FROM mutex WHERE name = :name)
            """
        statement = text(sql).bindparams(id=random_id(), name=mutex, state=MutexState.READY)
        db.session.execute(statement)
        db.session.commit()
    # config values for dart_client_key/secret are extracted.
    if AUTH_CONFIG.get('use_auth'):
        if AUTH_CONFIG.get('dart_client_key') and AUTH_CONFIG.get('dart_client_secret'):
            _credential = AUTH_CONFIG.get('dart_client_key')
            _secret = AUTH_CONFIG.get('dart_client_secret')
        else:
            raise Exception('dart_client_key and dart_client_secret must both exist.')
    else:
        # The credential/secret default values are set in order to prevent exception while calculating to hmac.
        _credential = 'cred'
        _secret = 'secret'
    # We set a user for dart_client with a apikey/secret (read from config) so that dart_client can work.
    # api auth expects a user to exist in the user table and have an entry in the api_key table (with key/secret values set).
    populate_dart_client_user(DART_CLIENT_NAME)
    populate_dart_client_apikeys(_credential, _secret, DART_CLIENT_NAME)
    # populate user and keys for external service (not dart client)
    populate_user_api_secret_keys()
    return 'OK'


@admin_bp.route('/populate_roles', methods=['post'])
@login_required
@required_roles(['Create'])
@jsonapi
def populate_roles():
    request_token = (request.get_json() or {}).get('token')
    ps_token = request_token or PERMISSION_CONFIG.get('token')

    is_success = False
    inputs = {}
    try:
        roles_2_ids, user_2_roles = getPermissionServiceRolesAndIds(
            host=PERMISSION_CONFIG.get('host'),
            app_name=PERMISSION_CONFIG.get('app_name'),
            token=ps_token)
        inputs['role_id_names'] = roles_2_ids
        inputs['user_2_roles'] = user_2_roles

        _logger.info('role_id_names = {roles_2_ids}'.format(roles_2_ids=roles_2_ids))
        _logger.info('user_2_roles = {user_2_roles}'.format(user_2_roles=user_2_roles))

        is_success = clear_roles_table() and \
                     populate_roles_table(inputs['role_id_names']) and \
                     populate_user_roles_table(inputs['user_2_roles'])

    except Exception as err:
        _logger.error('Input {inputs} failed to populate or it is in wrong format. err={err}'.format(inputs=inputs, err=err))

    if is_success:
        return {'results': 'OK'}, 200
    else:
        return {'results': 'Failure'}, 500
