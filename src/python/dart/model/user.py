from dart.model.base import BaseModel, dictable

@dictable
class User(BaseModel):
    def __init__(self, id, email, first_name, last_name, is_authenticated, session_expiration):
        """
        :type user_id: str
        :type email: str
        :type first_name: str
        :type last_name: str
        :type is_authenticated: bool
        :type session_expiration: datetime.datetime
        """
        self.id = id
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.is_authenticated = is_authenticated
        self.session_expiration = session_expiration
        self.is_active = True

    def get_id(self):
        return self.id
