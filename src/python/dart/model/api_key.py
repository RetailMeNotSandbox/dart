from dart.model.base import BaseModel, dictable

@dictable
class ApiKey(BaseModel):
    def __init__(self, id, user_id, api_key, api_secret):
        """
        :type user_id: str
        :type api_key: str
        :type api_secret: str
        """
        self.id = id
        self.user_id = user_id
        self.api_key = api_key
        self.api_secret = api_secret
