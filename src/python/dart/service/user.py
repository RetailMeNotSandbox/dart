from datetime import datetime
import logging
from sqlalchemy import DateTime, desc
from dart.context.locator import injectable
from dart.context.database import db
from dart.service.patcher import patch_difference, retry_stale_data
from dart.util.rand import random_id
from dart.model.orm import UserDao


_logger = logging.getLogger(__name__)


@injectable
class UserService(object):
    def __init__(self):
        pass

    @staticmethod
    def save_user(user, commit=True, flush=False):
        """ :type user: dart.model.user.User """
        user_dao = UserDao()
        for key, value in user.to_dict().iteritems():
            setattr(user_dao, key, value)
        if not user_dao.id:
            user_dao.id = random_id()
        db.session.merge(user_dao)
        if flush:
            db.session.flush()
        if commit:
            db.session.commit()
        return user_dao.to_model()

    @staticmethod
    def get_user(user_id, raise_when_missing=True):
        """ :rtype: dart.model.user.User """
        user_dao = UserDao.query.get(user_id)
        if not user_dao and raise_when_missing:
            raise Exception('user with id=%s not found' % user_id)
        return user_dao.to_model() if user_dao else None

    @staticmethod
    def get_user_by_email(email, raise_when_missing=True):
        """ :rtype: dart.model.user.User """
        user_dao = UserDao.query.filter(UserDao.email.like(email)).first()
        if not user_dao and raise_when_missing:
            raise Exception('user with email=%s not found' % email)
        return user_dao.to_model() if user_dao else None

    @staticmethod
    def login_user(user, is_authenticated, session_expiration):
        user.is_authenticated = (is_authenticated and user.session_expiration > datetime.utcnow())
        user.session_expiration = session_expiration
        UserService.save_user(user)
        return user

    @staticmethod
    def logout_user(user):
        user.session_expiration = datetime.utcnow()
        user.is_authenticated = False
        UserService.save_user(user)
        return user
