import os
import shutil
import time
import tempfile
import shutil
import docker
import collections
import tarfile
from subprocess import call
from flask import Flask, request, redirect, url_for, render_template, abort, jsonify, make_response
from werkzeug.utils import secure_filename
from werkzeug.contrib.fixers import ProxyFix
from werkzeug.exceptions import HTTPException
from config import config

#
# Theses location should works out-of-box if you use default settings
#
thispath = os.path.dirname(os.path.realpath(__file__))
BASEPATH = os.path.join(thispath)

app = Flask(__name__)
app.url_map.strict_slashes = False

logs = {}
status = {}

#
# Helpers
#
def notice(shortname, message):
    status[shortname]['console'] += "\n>>> %s\n" % message

def execute(shortname, target, command):
    for line in target.exec_run(command, stream=True):
        # debug to console
        print("[%s] %s" % (target, line.strip().decode('utf-8')))

        # append to status
        status[shortname]['console'].append(line.decode('utf-8'))
        logs[shortname] += line.decode('utf-8')

def consoleof(console):
    output = ""

    for line in console:
        output += line

    return output

#
# Extract the kernel from a container
# if release is True, kernel is compiled from initramfs
# otherwise it's compiled from a core change
#
def kernel(target, branch, release):
    stream, stat = target.get_archive('/target')

    # format kernel "g8os-BRANCH-generic.efi" if it's a release
    suffix = '-generic' if release else ""
    kname = "g8os-%s%s.efi" % (branch, suffix)

    print("[+] exporting kernel: %s", kname)

    with tempfile.TemporaryDirectory() as tmpdir:
        archive = os.path.join(tmpdir, "archive.tar")

        # downloading archive from docker
        with open(archive, 'wb') as f:
            f.write(stream.read())

        print(tmpdir)

        # extracting archive
        tar = tarfile.open(archive, 'r')
        tar.extractall(tmpdir)
        tar.close()

        # now we have the kernel on our tmpdir
        # let's copy it to the right location
        krnl = os.path.join(tmpdir, "target", "vmlinuz.efi")
        dest = os.path.join(config['KERNEL_TARGET'], kname)

        if not os.path.isfile(krnl):
            return False

        print("[+] moving kernel into production")
        os.rename(krnl, dest)

    return True

#
# Events
#
def event_ping(payload):
    print("[+] repository: %s" % payload['repository']['full_name'])
    return "OK"

def event_push(payload):
    repository = payload['repository']['full_name']
    ref = payload['ref']
    branch = os.path.basename(ref)
    client = docker.from_env()
    shortname = "%s/%s" % (repository, branch)

    print("[+] repository: %s, branch: %s" % (repository, branch))

    #
    # This is a little bit hardcoded for our side
    #
    if repository == "g8os/core0":
        #
        pass

    # if repository == "g8os/initramfs":
    if repository == "maxux/hooktest":
        #
        # This is a main project, we build it
        # then make a base image from it
        #
        target = client.containers.run("ubuntu:16.04", tty=True, detach=True)

        # reset logs and setting up status
        logs[shortname] = ""
        status[shortname] = {
            'docker': target.id,
            'status': 'running',
            'console': collections.deque(maxlen=20),
        }

        notice(shortname, 'Preparing system')
        execute(shortname, target, "apt-get update")
        execute(shortname, target, "apt-get install -y git")

        notice(shortname, 'Cloning repository')
        execute(shortname, target, "git clone -b '%s' https://github.com/%s" % (branch, repository))

        notice(shortname, 'Executing script')
        remote = os.path.basename(repository)
        execute(shortname, target, "bash /%s/autobuild/gig-build.sh" % remote)

        kernel(target, branch, True)

        # create image from that branch

        target.remove(force=True)
        status[shortname]['status'] = 'done'

    return "OK"

#
# Routing
#
@app.route('/build/logs/<project>/<name>/<branch>', methods=['GET'])
def global_logs(project, name, branch):
    collapse = "%s/%s/%s" % (project, name, branch)
    if not logs.get(collapse):
        abort(404)

    response = make_response(logs[collapse])
    response.headers["Content-Type"] = "plain/text"

    return response

@app.route('/build/status', methods=['GET'])
def global_status():
    output = {}

    for key, item in status.items():
        output[key] = {
            'status': item['status'],
            'monitor': consoleof(item['console']),
            'docker': item['docker'][0:8],
        }

    return jsonify(output)

@app.route('/build/<project>/hook', methods=['GET', 'POST'])
def ipxe_branch_network(project):
    print("[+] project: %s" % project)

    if not request.headers.get('X-Github-Event'):
        abort(400)

    payload = request.get_json()
    print(payload)

    if request.headers['X-Github-Event'] == "ping":
        print("[+] ping event")
        return event_ping(payload)

    if request.headers['X-Github-Event'] == "push":
        print("[+] push event")
        return event_push(payload)

    print("[-] unknown event: %s" % request.headers['X-Github-Event'])
    abort(400)

print("[+] listening")
app.run(host="0.0.0.0", port=config['HTTP_PORT'], debug=config['DEBUG'], threaded=True)

