from flask_login import current_user
from dart.model.accounting import ActivityEntity, Accounting


def generate_accounting_event(return_code, req):
    user_id = current_user.email
    if not user_id:
        user_id = 'anonymous'

    state = req.method  # GET/POST/PUT/PATCH/DELETE

    # E.g. /api/1/engine
    path = str(req.path)
    api_version = path.split('/')[2] if len(path) > 3 else '1'  # 1 is the default API version

    # Sanitize URI params. Activities (e.g engine, dataset...) remain and everything else is replaced ('param')
    entity = '/'.join([act if act in ActivityEntity.all() else 'param' for act in path.split('/')[3:]])

    # Params will be saved in a json structure.
    # Make of URI params (e.g. /x/param-1/y), URL params (e.g. www.abc.com?param-1=value-1&p2=v2
    # and the json body
    params = {
        # Anything not "known" (e.g. datastore, graph, action) is removed and the URI params are left.
        'URI': [act for act in str(req.path).split('/')[3:] if act not in ActivityEntity.all()],
        # turning the url params to a dictionary
        'URL': dict([p.split('=') if '=' in p else [p, ''] for p in
                     req.query_string.split('&')]) if req.query_string else {},
        # passing the json_body as is.
        'json_body': req.get_json() if req.get_json() is not None else {}

    }
    # Saving the accounting table record takes place here.
    accounting_event = Accounting(user_id=user_id,
                                  state=state,
                                  entity=entity,
                                  params=params,
                                  return_code=return_code,
                                  api_version=api_version)
    return accounting_event