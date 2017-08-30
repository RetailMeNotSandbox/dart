import os

from flask import Blueprint, send_from_directory
from flask.ext.login import login_required

index2_bp = Blueprint('index2', __name__, static_folder='ui2/build')


@index2_bp.route('/2/', defaults={'path': ''})
@index2_bp.route('/2/<path:path>')
@login_required
def serve(path):
    if path == "":
        return send_from_directory('ui2/build', 'index.html')
    else:
        if os.path.exists("ui2/build/" + path):
            return send_from_directory('ui2/build', path)
        else:
            return send_from_directory('ui2/build', 'index.html')
