''' Handles default values that should be added to the user/apiKey tables to allow apicalls authentication '''
from sqlalchemy import text
from dart.context.database import db

def exec_sql(statement):
    db.session.execute(statement)
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
    ''' dart client has a fixed name dart@client.rmn  '''
    sql = """DELETE FROM public.user  WHERE (email = :email) """
    exec_sql(text(sql).bindparams(email=dart_client_user))

    sql = """ INSERT INTO public.user (id, version_id, created, updated, email, first_name, last_name, is_authenticated, session_expiration)
              SELECT :id, 0, NOW(), NOW(), :email, :email, :email, FALSE , NOW()"""
    exec_sql(text(sql).bindparams(id=dart_client_user, email=dart_client_user))
