from dart.model.exception import DartAuthenticationException

from basicauth import decode


def basic_auth(auth_header, api_key_service, user_service):
    # we expect a basic Authorization header: "Basic base64('api_key,secret_key')"
    # E.g. auth_header = encode('rdegges', 'omghax!!!') ## => auth_header = 'Basic cmRlZ2dlczpvbWdoYXglMjElMjElMjE='
    # E.g. api_key, secret_key = decode(auth_header) ## ==> 'rdegges', 'omghax!!!'
    api_key_value, secret_key_value = decode(auth_header)

    api_key_record = api_key_service.get_api_key(api_key_value, False)
    if not api_key_record:
        raise DartAuthenticationException(
            'DART is unable to authenticate your request, api_key missing or not found. api_key=%s' % api_key_value)

    user_record = user_service.get_user_by_email(api_key_record.user_id, False)
    if not user_record:
        raise DartAuthenticationException(
            'DART is unable to authenticate your request, user not found. user_id=%s' % api_key_record.user_id)

    # Authenticated means: 1. We found the user in the user table, 2. The secret key is matching the one in the api_key table.
    user_record.is_authenticated = api_key_record.api_secret and (api_key_record.api_secret == secret_key_value)

    if not user_record.is_authenticated:
        raise DartAuthenticationException('DART is unable to authenticate your request')

    return user_record