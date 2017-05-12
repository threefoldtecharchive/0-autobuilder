import os
import shutil
import time
import tempfile
import shutil
import docker
import collections
import tarfile
import json
import traceback
from subprocess import call
from flask import Flask, request, redirect, url_for, render_template, abort, jsonify, make_response
from werkzeug.utils import secure_filename
from werkzeug.contrib.fixers import ProxyFix
from werkzeug.exceptions import HTTPException
from config import config

#
# FIXME FIXME FIXME
# ===============================================
# Refactore me please, this should use classes and not a flat file like this
# I'm really ugly.
# ===============================================
# FIXME FIXME FIXME
#

#
# Theses location should works out-of-box if you use default settings
#
thispath = os.path.dirname(os.path.realpath(__file__))
BASEPATH = os.path.join(thispath)

if not os.path.exists(config['LOGS_DIRECTORY']):
    os.mkdir(config['LOGS_DIRECTORY'])

app = Flask(__name__, static_url_path='/monitor')
app.url_map.strict_slashes = False

logs = {}
status = {}

#
# History
#
def history_get():
    return json.loads(history_raw())

def history_raw():
    filepath = os.path.join(config['LOGS_DIRECTORY'], "history.json")

    if not os.path.isfile(filepath):
        return "[]\n"

    with open(filepath, "r") as f:
        contents = f.read()

    if not contents:
        contents = "[]\n"

    return contents

def history_push(shortname):
    history = history_get()

    item = {
        'name': shortname,
        'status': status[shortname]['status'],
        'monitor': consoleof(status[shortname]['console']),
        'docker': status[shortname]['docker'][0:10],
        'started': status[shortname]['started'],
        'ended': status[shortname]['ended'],
        'error': status[shortname]['error'],
        'commits': status[shortname]['commits'],
        'artifact': status[shortname]['artifact'],
    }

    history.insert(0, item)

    filepath = os.path.join(config['LOGS_DIRECTORY'], "history.json")

    with open(filepath, "w") as f:
        f.write(json.dumps(history))



#
# Helpers
#
def notice(shortname, message):
    status[shortname]['console'].append("\n>>> %s\n" % message)

def execute(shortname, target, command):
    dockid = target.id[0:10]

    for line in target.exec_run(command, stream=True, stderr=True):
        # debug to console
        print("[%s] %s" % (dockid, line.strip().decode('utf-8')))

        # append to status
        status[shortname]['console'].append(line.decode('utf-8'))
        logs[shortname] += line.decode('utf-8')

def consoleof(console):
    output = ""

    for line in console:
        output += line

    return output

def imagefrom(client, repository, branch):
    for image in client.images.list():
        if len(image.tags) == 0:
            continue

        # checking if we have a tag which start with the branch
        temp = image.tags[0].split(':')
        name = temp[0]
        tag  = temp[1]

        # this image have nothing to do with this repo
        if name != repository:
            continue

        # this image is not the right version
        if branch.startswith(tag):
            return image

    return None



#
# build status
#
def buildsuccess(shortname):
    status[shortname]['status'] = 'success'
    status[shortname]['ended'] = int(time.time())
    history_push(shortname)

    del status[shortname]

    return "OK"

def builderror(shortname, message):
    print("[-] %s: %s" % (shortname, message))

    status[shortname]['status'] = 'error'
    status[shortname]['error'] = message
    status[shortname]['ended'] = int(time.time())
    history_push(shortname)

    del status[shortname]

    return "FAILED"

#
# Extract the kernel from a container
# if release is True, kernel is compiled from initramfs
# otherwise it's compiled from a core change
#
def kernel(shortname, tmpdir, branch, reponame, commit, release):
    # format kernel "g8os-BRANCH-generic.efi" if it's a release
    suffix = 'generic' if release else "%s-%s" % (reponame, commit)
    kname = "g8os-%s-%s.efi" % (branch, suffix)

    print("[+] exporting kernel: %s" % kname)

    # now we have the kernel on our tmpdir
    # let's copy it to the right location
    krnl = os.path.join(tmpdir.name, "vmlinuz.efi")
    dest = os.path.join(config['KERNEL_TARGET'], kname)

    if not os.path.isfile(krnl):
        return False

    print("[+] moving kernel into production")
    os.rename(krnl, dest)

    if not release:
        basename = "g8os-%s.efi" % branch
        target = os.path.join(config['KERNEL_TARGET'], basename)

        if os.path.islink(target) or os.path.isfile(target):
            os.remove(target)

        # moving to kernel directory
        now = os.getcwd()
        os.chdir(config['KERNEL_TARGET'])

        # symlink last kernel to basename
        os.symlink(kname, basename)
        os.chdir(now)

    status[shortname]['artifact'] = kname

    return True



#
# Build workflow
#
def build(shortname, baseimage, repository, script, branch, reponame, commit, release):
    # connecting docker
    client = docker.from_env()

    # creating temporary workspace
    tmpdir = tempfile.TemporaryDirectory(prefix="initramfs-", dir=config['TMP_DIRECTORY'])
    print("[+] temporary directory: %s" % tmpdir.name)

    #
    # This is a main project, we build it
    # then make a base image from it
    #
    print("[+] starting container")
    volumes = {tmpdir.name: {'bind': '/target', 'mode': 'rw'}}
    target = client.containers.run(baseimage, tty=True, detach=True, volumes=volumes)

    status[shortname]['status'] = 'initializing'
    status[shortname]['docker'] = target.id

    if release:
        notice(shortname, 'Preparing system')
        execute(shortname, target, "apt-get update")
        execute(shortname, target, "apt-get install -y git")

        notice(shortname, 'Cloning repository')
        execute(shortname, target, "git clone -b '%s' https://github.com/%s" % (branch, repository))

    notice(shortname, 'Executing script')
    status[shortname]['status'] = 'building'

    try:
        # FIXME: should not happen
        if not release:
            execute(shortname, target, "sh -c 'cd /initramfs && git pull'")

        # compiling
        execute(shortname, target, "bash /initramfs/autobuild/%s %s" % (script, branch))

        if not os.path.isfile(os.path.join(tmpdir.name, "vmlinuz.efi")):
            raise RuntimeError("Kernel not found on %s/vmlinuz.efi" % tmpdir.name)

        # extract kernel
        kernel(shortname, tmpdir, branch, reponame, commit, False)

        if release:
            # commit to baseimage
            status[shortname]['status'] = 'committing'
            target.commit(repository, branch)

        # build well done
        buildsuccess(shortname)

    except Exception as e:
        traceback.print_exc()
        builderror(shortname, str(e))

    # end of build process
    target.remove(force=True)
    tmpdir.cleanup()

    return "OK"

#
# Events
#
def event_ping(payload):
    print("[+] repository: %s" % payload['repository']['full_name'])
    return "OK"

def event_push(payload):
    # extracting data from payload
    repository = payload['repository']['full_name']
    ref = payload['ref']
    branch = os.path.basename(ref)
    shortname = "%s/%s" % (repository, branch)
    commit = payload['head_commit']['id'][0:8]

    # connecting docker
    client = docker.from_env()

    # saving full log to a file
    # logfile = os.path.join(config['LOGS_DIRECTORY']...

    # extract repository name
    reponame = os.path.basename(repository)

    print("[+] repository: %s, branch: %s" % (repository, branch))

    # checking for existing tasks
    if status.get(shortname):
        if status[shortname]['status'] not in ['success', 'error']:
            print("[-] task already running, ignoring")
            return "BUSY"

    # creating entry for that build
    logs[shortname] = ""
    status[shortname] = {
        'docker': "",
        'status': 'preparing',
        'console': collections.deque(maxlen=20),
        'started': int(time.time()),
        'ended': None,
        'error': None,
        'commits': payload['commits'],
        'artifact': None,
        # 'logfile':
    }

    #
    # This is a little bit hardcoded for our side
    #
    if repository == "g8os/core0":
        baseimage = imagefrom(client, "g8os/initramfs", branch)
        if not baseimage:
            return builderror(shortname, 'No base image found for branch: %s' % branch)

        print("[+] base image found: %s" % baseimage.tags)
        return build(shortname, baseimage.id, repository, "gig-build-cores.sh", branch, reponame, commit, False)

    if repository == "g8os/g8ufs":
        baseimage = imagefrom(client, "g8os/initramfs", branch)
        if not baseimage:
            return builderror(shortname, 'No base image found for branch: %s' % branch)

        print("[+] base image found: %s" % baseimage.tags)
        return build(shortname, baseimage.id, repository, "gig-build-g8ufs.sh", branch, reponame, commit, False)

    if repository == "g8os/initramfs-gig":
        baseimage = imagefrom(client, "g8os/initramfs", branch)
        if not baseimage:
            return builderror(shortname, 'No base image found for branch: %s' % branch)

        print("[+] base image found: %s" % baseimage.tags)
        return build(shortname, baseimage.id, repository, "gig-build-extensions.sh", branch, reponame, commit, False)

    if repository == "g8os/initramfs":
        return build(shortname, "ubuntu:16.04", repository, "gig-build.sh", branch, reponame, commit, True)

    builderror(shortname, "Unknown repository, we don't follow this one.")
    abort(404)



#
# Routing
#
@app.route('/build/logs/<project>/<name>/<branch>', methods=['GET'])
def global_logs(project, name, branch):
    collapse = "%s/%s/%s" % (project, name, branch)
    if not logs.get(collapse):
        abort(404)

    response = make_response(logs[collapse])
    response.headers["Content-Type"] = "text/plain"

    return response

@app.route('/build/status', methods=['GET'])
def global_status():
    output = {}

    for key, item in status.items():
        output[key] = {
            'status': item['status'],
            'monitor': consoleof(item['console']),
            'docker': item['docker'][0:10],
            'started': item['started'],
            'ended': item['ended'],
            'error': item['error'],
            'commits': item['commits'],
            'artifact': item['artifact'],
        }

    return jsonify(output)

@app.route('/build/history', methods=['GET'])
def global_history():
    response = make_response(history_raw())
    response.headers["Content-Type"] = "application/json"

    return response

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

@app.route("/monitor/", strict_slashes=False)
def index():
    return render_template("index.html")

print("[+] listening")
app.run(host="0.0.0.0", port=config['HTTP_PORT'], debug=config['DEBUG'], threaded=True)

