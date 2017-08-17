''' Handles default values that should be added to the user/apiKey tables to allow apicalls authentication '''
from sqlalchemy import text
from dart.context.database import db
import json
import requests
import logging

_logger = logging.getLogger(__name__)

def exec_sql(statement, is_commit=True):
    db.session.execute(statement)
    if is_commit:
      db.session.commit()


def populate_dart_client_apikeys(credential, secret, dart_client_user):
    ''' based on auth.dart_client_key and auth.dart_secret_key from config file. '''
    del_sql = """ DELETE FROM public.api_key  WHERE (user_id = :user_id) """
    exec_sql(text(del_sql).bindparams(user_id=dart_client_user))


    add_sql = """INSERT INTO public.api_key(id, version_id, created, updated, user_id, api_key, api_secret)
      SELECT :id, 0, NOW(), NOW(),:user_id, :dart_client_key, :dart_client_secret
    """
    statement = text(add_sql).bindparams(id=dart_client_user,
                                     user_id=dart_client_user,
                                     dart_client_key=credential,
                                     dart_client_secret=secret)
    exec_sql(statement)


def populate_dart_client_user(dart_client_user):
    ''' dart client has a fixed name '''
    sql = """DELETE FROM public.user  WHERE (email = :email) """
    exec_sql(text(sql).bindparams(email=dart_client_user))

    sql = """ INSERT INTO public.user (id, version_id, created, updated, email, first_name, last_name, is_authenticated, session_expiration)
              SELECT :id, 0, NOW(), NOW(), :email, :email, :email, FALSE , NOW()"""
    exec_sql(text(sql).bindparams(id=dart_client_user, email=dart_client_user))


def clear_roles_table():
    exec_sql("BEGIN;", False)

    try:
      sql = """DELETE FROM authorization_roles """
      exec_sql(text(sql))

      sql = """ DELETE FROM user_roles """
      exec_sql(text(sql))
    except Exception as err:
        _logger.error("Failed to truncate authorization_roles and user_roles tables: error={err}".format(err=err))
        exec_sql("ROLLBACK;", False)
        return False

    return True

# {role_id1:role_name1, role_id2:role_name2}
def populate_roles_table(role_id_names):
    try:
      for id, name in role_id_names.iteritems():
        sql = """ INSERT INTO public.authorization_roles(role_id, role_name)
                  values (:role_id, :role_name)"""
        exec_sql(text(sql).bindparams(role_id=id, role_name=name))
    except Exception as err:
        _logger.error("Failed to populate roles id/names in authorization_roles table: error={err}".format(err=err))
        exec_sql("ROLLBACK;", False)
        return False

    return True


# E.g. {"role_id_names":{"111":"aaa","22":"bb","3":"c"},"user_2_roles":{"aaa@rmn.com":{"action_roles":["111","22"],"membership_roles":["22"]},"bbb@rmn.com":{"action_roles":["111"],"membership_roles":["3"]}}}
def populate_user_roles_table(user_2_roles):
    try:
      for id, roles in user_2_roles.iteritems():
          sql = """ INSERT INTO public.user_roles(user_id, action_roles, membership_roles)
                    VALUES (:user_id, :action_roles, :membership_roles) """
          exec_sql(text(sql).bindparams(user_id=id,
                                        action_roles=json.dumps(roles["action_roles"]),
                                        membership_roles=json.dumps(roles["membership_roles"])))
    except Exception as err:
        _logger.error("Failed to populate user_roles table: error={err}".format(err=err))
        exec_sql("ROLLBACK;", False)
        return False

    exec_sql("COMMIT;")
    return True

def getPermissionServiceRolesAndIds(host, app_name, token):
    url = "https://{host}/ws/role/application/{app_name}".format(host=host, app_name=app_name)
    AUTH_HEADER = {
        'Authorization': "{token}".format(token=token),
        'Content-Type': 'application/json'
    }

    # Get all roles (and their id) per application name
    # We need the id-name mapping because querying user's roles returns ids (both app and role id)
    role_id_names = {}
    role_id_namesreq = requests.get(url, headers=AUTH_HEADER)
    if (role_id_namesreq.status_code == 401):
        _logger.error("Need new token: error={code}".format(code=role_id_namesreq.status_code))

    for role in role_id_namesreq.json():
        role_id_names[role["id"]] = role["displayName"]
    _logger.info("1. role_id_names = {role_id_names}".format(role_id_names=role_id_names))

    # Get all app_name app users to retrieve roles for
    url = "https://{host}/ws/application/{app_name}/usernames".format(host=host, app_name=app_name)
    users_req = requests.get(url, headers=AUTH_HEADER)
    users = users_req.json()
    _logger.info("2. users = {users}".format(users=users))

    # Get app id from its name
    url = "https://{host}/ws/application/{app_name}".format(host=host, app_name=app_name)
    app_id = requests.get(url, headers=AUTH_HEADER).json()["id"]
    _logger.info("3. app_id = {app_id}".format(app_id=app_id))

    # get all roles per app that a user has
    # Roles that start with Can_ are action roles and roles that start with Is_Member_Of_ are membership roles.
    # The distinction is handy to figure out what a user can do and whether it can do it on an object based on team ownership
    user_2_roles = {}
    for user in users:
        url = "https://{host}/ws/user/{user}".format(host=host, user=user)
        user_roles = requests.get(url, headers=AUTH_HEADER).json()

        membership_roles = []
        action_roles = []
        for user_app_role_id in user_roles["applicationRoles"][app_id]:
            user_app_role_name = role_id_names[user_app_role_id]
            if user_app_role_name.startswith("Can_"):
                action_roles.append(user_app_role_name)
            elif user_app_role_name.startswith("Is_Member_Of_"):
                membership_roles.append(user_app_role_name)

        user_2_roles[user] = {
            "action_roles": action_roles,
            "membership_roles": membership_roles
        }
        _logger.info("4. user {user} roles = {user_2_roles}".format(user=user, user_2_roles=user_2_roles[user]))

    return role_id_names, user_2_roles
