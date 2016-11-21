from flask import Blueprint, render_template, session
from flask.ext.login import login_required

index_bp = Blueprint('index', __name__)


@index_bp.route('/')
@login_required
def index():
    return render_template('index.html')


@index_bp.route('/info')
def info():
    return render_template('info.html')
