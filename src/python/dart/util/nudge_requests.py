import requests
from dart.model.exception import DartRequestException


def make_nudge_request(url, json):
    response = requests.post(url=url,
                             json=json)
    raise_if_response_invalid(response)
    return response


def raise_if_response_invalid(response):
    if response.status_code != 200:
        raise DartRequestException(response)
