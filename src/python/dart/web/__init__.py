import logging
import logging.config
import imp
import os
import urllib
import urlparse
import uuid
import yaml

from flask import Flask, jsonify, redirect, request

from dart.config.config import configuration
from dart.context.context import AppContext
from dart.context.database import db
from dart.model.exception import DartValidationException, DartAuthenticationException
from dart.web.api.graph import api_graph_bp
from dart.web.ui.admin.admin import admin_bp
from dart.web.api.auth import login_manager, auth_bp
from dart.web.api.action import api_action_bp
from dart.web.api.dataset import api_dataset_bp
from dart.web.api.datastore import api_datastore_bp
from dart.web.api.engine import api_engine_bp
from dart.web.api.event import api_event_bp
from dart.web.api.schema import api_schema_bp
from dart.web.api.trigger import api_trigger_bp
from dart.web.api.workflow import api_workflow_bp
from dart.web.api.subscription import api_subscription_bp
from dart.web.ui.index import index_bp
from flask.ext.login import login_required

from jinja2 import Environment, FileSystemLoader
import os

_logger = logging.getLogger(__name__)

# Onelogin is expecting some of its config via files.
# we populate these files in this function.
def write_onelogin_settings():
    # Capture our current directory, the onelogin settings.json is in relative path ./ui/onelogin
    # we write the config file to /tmp so we can use an absolute path
    THIS_DIR = os.path.dirname(os.path.abspath(__file__))

    j2_env = Environment(loader=FileSystemLoader(THIS_DIR + "/ui/onelogin/"),
                         trim_blocks=True)
    file_str = j2_env.get_template('settings.json.tmpl').render(
        appid=app.config.get('auth').get('appid'),
        onelogin_server=config.get('auth').get('onelogin_server'),
        private_key=config.get('auth').get('private_key'),
        x509cert=config.get('auth').get('x509cert'),
        dart_server=config.get('auth').get('dart_server')
    )

    f = open('./ui/onelogin' + '/settings.json', 'w')
    f.write(file_str)
    f.close()




api_version_prefix = '/api/1'
config_path = os.environ['DART_CONFIG']
config = configuration(config_path)
logging.config.dictConfig(config['logging'])
_logger.info('loaded config from path: %s' % config_path)


app = Flask(__name__, template_folder='ui/templates', static_folder='ui/static')

app.dart_context = AppContext(
    config=config,
    exclude_injectable_module_paths=[
        'dart.message.engine_listener',
        'dart.message.trigger_listener',
        'dart.message.subscription_listener'
    ]
)

app.config.update(config['flask'])
app.config['SECRET_KEY'] = str(uuid.uuid4()) # not related to onelogin's secret key, its a flask secret key.
db.init_app(app)

app.config['auth'] = config['auth']
write_onelogin_settings()

if (app.config['auth'] and app.config['auth'].get('use_auth') == False):
  app.config['LOGIN_DISABLED'] = True


app.auth_module = imp.load_source(config['auth']['module'], config['auth'].get('module_source'))
app.auth_class = getattr(app.auth_module, config['auth']['class'])
login_manager.init_app(app)

app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(api_dataset_bp, url_prefix=api_version_prefix)
app.register_blueprint(api_datastore_bp, url_prefix=api_version_prefix)
app.register_blueprint(api_engine_bp, url_prefix=api_version_prefix)
app.register_blueprint(api_action_bp, url_prefix=api_version_prefix)
app.register_blueprint(api_trigger_bp, url_prefix=api_version_prefix)
app.register_blueprint(api_workflow_bp, url_prefix=api_version_prefix)
app.register_blueprint(api_subscription_bp, url_prefix=api_version_prefix)
app.register_blueprint(api_event_bp, url_prefix=api_version_prefix)
app.register_blueprint(api_schema_bp, url_prefix=api_version_prefix)
app.register_blueprint(api_graph_bp, url_prefix=api_version_prefix)
app.register_blueprint(index_bp)


@app.route('/apidocs')
@app.route('/apidocs/')
@app.route('/apidocs/index.html')
@login_required
def get_apidocs():
    swagger_ui_url = urlparse.urljoin(request.base_url, '/static/apidocs/index.html?' + urllib.urlencode({
        'url': urlparse.urljoin(request.base_url, '/api/1/swagger.json')
    }))
    return redirect(swagger_ui_url)


@app.route('/api/1/swagger.json', methods=['GET'])
@login_required
def get_swagger():
    swagger_spec = yaml.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               'api',
                                               'swagger.yaml'), 'rt'))
    # Update the swagger specification to include specific information
    # about where the API is being served on this server
    swagger_spec['host'] = request.host
    swagger_spec['basePath'] = '/api/1'
    swagger_spec['schemes'] = [request.scheme]
    return jsonify(swagger_spec)


@app.errorhandler(DartValidationException)
def handle_dart_validation_exception(e):
    response = jsonify({'results': 'ERROR', 'error_message': e.message})
    response.status_code = 400
    return response


@app.errorhandler(DartAuthenticationException)
def handle_dart_authentication_errors(e):
    response = jsonify({'restults': 'Error', 'error_message': 'DART was unable to authenticate your request'})
    response.status_code = 401
    return response


@app.after_request
def set_dart_version_cookie(response):
    response.set_cookie('dart.web.version', os.environ.get('DART_WEB_VERSION', 'unknown'))
    return response
