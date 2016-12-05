
# Copyright (C) 2016  Ghent University
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# pylint: disable=c0111,c0301,c0325,c0103
# !/usr/bin/env python3

import os
import json
import yaml
import tempfile
from subprocess import check_call, check_output, STDOUT, CalledProcessError
from controllers import maas, aws

from flask import abort


USER = os.environ.get('JUJU_ADMIN_USER')
PASSWORD = os.environ.get('JUJU_ADMIN_PASSWORD')


class JuJu_Token(object):
    def __init__(self, auth, c_name, c_type, c_access, c_token):
        self.username = auth.username
        self.password = auth.password
        self.c_name = c_name
        self.c_type = c_type
        self.c_access = c_access
        self.c_token = c_token
        self.m_name = None
        self.m_access = None

    def set_model(self, modelname, modelaccess):
        self.m_name = modelname
        self.m_access = modelaccess

    def m_shared_name(self):
        return "{}/{}".format(USER, self.m_name)


def authenticate(auth, controller, modelname=None):
    try:
        check_output(['juju', 'login', auth.username, '--controller', controller], input=auth.password + '\n',
                 universal_newlines=True)
    except CalledProcessError:
        abort(403)
    controllers_info = json.loads(check_output(['juju', 'controllers', '--format', 'json']))
    with open("/home/ubuntu/.local/share/juju/clouds.yaml", 'r') as y_clouds:
        clouds = yaml.load(y_clouds)
    c_type = clouds['clouds'][controller]['type']
    c_endpoint = clouds['clouds'][controller]['endpoint']
    c_access = controllers_info['controllers'][controller]['access']
    if c_type == 'MAAS':
        try:
            c_token = maas.MAAS_Token(c_endpoint, auth)
            maas.login(auth)
            token = JuJu_Token(auth, controller, c_type, c_access, c_token)
        except CalledProcessError:
            abort(403)

    if modelname:
        models_info = json.loads(check_output(['juju', 'models', '--format', 'json']))
        token.set_model(modelname, models_info[0]['models']['users'][token.username]['access'])
    check_call(['juju', 'logout'])
    check_output(['juju', 'login', USER, '--controller', token.c_name], input=PASSWORD + '\n',
             universal_newlines=True)
    if token.m_name:
        check_call(['juju', 'switch', token.m_name])
    return token


def list_users():
    users = json.loads(check_output(['juju', 'list-users', '--format', 'json'],
                                    universal_newlines=True))
    return [u['user-name'] for u in users]


def create_user(username, password):
    check_call(['juju', 'add-user', username])
    check_call(['juju', 'grant', username, 'add-model'])
    output = None
    try:
        # We need to use check_output here because check_call has no "input" option
        output = check_output(['juju', 'change-user-password', username],
                              input="{}\n{}".format(password, password),
                              universal_newlines=True)
    except CalledProcessError as e:
        output = e.output
    finally:
        print(output)


def create_model(token, ssh_keys):
    if CONTROLLER_TYPE == 'maas':
        credentials = maas.get_credentials(CLOUD_NAME, token.username, token.api_key)
    else:
        credentials = aws.get_credentials(token)
    tmp = tempfile.NamedTemporaryFile(mode="w+", delete=False)
    tmp.write(json.dumps(credentials))
    tmp.close()  # deletes the file
    modelconfig = []
    if ssh_keys:
        modelconfig = modelconfig + ['authorized-keys="{}"'.format(ssh_keys)]
    if len(modelconfig):
        modelconfig = ['--config'] + modelconfig
    check_call(['juju', 'add-credential', '--replace', CLOUD_NAME, '-f', tmp.name])
    check_call(['juju', 'add-model', token.modelname, '--credential', token.username] + modelconfig)
    check_call(['juju', 'grant', token.username, 'admin', token.modelname])


def get_gui_url(token):
    modelname = 'controller'
    if token.modelname:
        modelname = token.modelname
    return check_output(['juju', 'gui', '--no-browser', '--model', modelname], universal_newlines=True, stderr=STDOUT).rstrip()


def status(token):
    output = check_output(['juju', 'status', '--format', 'json', '--model', token.modelname], universal_newlines=True)
    return json.loads(output)


def config(token, appname):
    output = check_output(['juju', 'config', appname, '--model', token.modelname, '--format', 'json'], universal_newlines=True)
    return json.loads(output)


def user_exists(username, modelname=None):
    exists = False
    if modelname:
        output = check_output(['juju', 'users', modelname, '--format', 'json'])
        if username in json.loads(output[:-1]):
            exists = True
    else:
        output = check_output(['juju', 'users', '--format', 'json'])
        if username in json.loads(output[1:-2]).values():
            exists = True
    return exists


def model_exists(token):
    exists = False
    data = json.loads(check_output(['juju', 'list-models', '--format', 'json']))
    for model in data['models']:
        if token.modelname == model['name']:
            exists = True
            break
    return exists


def get_credentials(token):
    if CONTROLLER_TYPE == "maas":
        credentials = maas.get_credentials(CLOUD_NAME, token.username, token.api_key)
    else:
        credentials = aws.get_credentials(token.username)
    return credentials


def get_clouds():
    if CONTROLLER_TYPE == "maas":
        clouds = maas.get_clouds(CLOUD_NAME)
    else:
        clouds = aws.get_clouds(CLOUD_NAME)
    return clouds
