from datetime import datetime
import logging
from sqlalchemy import DateTime, desc
from dart.context.locator import injectable
from dart.context.database import db
from dart.service.patcher import patch_difference, retry_stale_data
from dart.util.rand import random_id
from dart.model.orm import ApiKeyDao


_logger = logging.getLogger(__name__)


@injectable
class ApiKeyService(object):
    def __init__(self):
        pass

    @staticmethod
    def save_api_key(api_key, commit=True, flush=False):
        """ :type api_key: dart.model.api_key.ApiKey """
        key_dao = ApiKeyDao()
        for key, value in user.to_dict().iteritems():
            setattr(key_dao, key, value)
        if not key_dao.id:
            key_dao.id = random_id()
        db.session.merge(key_dao)
        if flush:
            db.session.flush()
        if commit:
            db.session.commit()
        return key_dao.to_model()

    @staticmethod
    def get_api_key(api_key, raise_when_missing=True):
        """ :rtype: dart.model.api_key.ApiKey """
        key_dao = ApiKeyDao.query.filter(ApiKeyDao.api_key.like(api_key)).first()
        if not key_dao and raise_when_missing:
            raise Exception('user with id=%s not found' % user_id)
        return key_dao.to_model() if key_dao else None
