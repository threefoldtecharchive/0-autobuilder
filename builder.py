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
import requests
import threading
from subprocess import call
from flask import Flask, request, redirect, url_for, render_template, abort, jsonify, make_response, Response
from werkzeug.utils import secure_filename
from werkzeug.contrib.fixers import ProxyFix
from werkzeug.exceptions import HTTPException
from config import config
from flist import AutobuilderFlistMonitor

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

if not os.path.exists(config['logs-directory']):
    os.mkdir(config['logs-directory'])

sublogfiles = os.path.join(config['logs-directory'], "commits")
if not os.path.exists(sublogfiles):
    os.mkdir(sublogfiles)

app = Flask(__name__, static_url_path='/static')
app.url_map.strict_slashes = False

monitor = AutobuilderFlistMonitor(config)

logs = {}
status = {}

buildstatus = {
    "success": "build succeed",
    "error": "build failed, please check report",
    "pending": "building...",
}


#
# History
#
def history_get(limit=None):
    return json.loads(history_raw(limit))

def history_raw(limit=None):
    filepath = os.path.join(config['logs-directory'], "history.json")

    if not os.path.isfile(filepath):
        return "[]\n"

    with open(filepath, "r") as f:
        contents = f.read()

    if limit is not None:
        temp = json.loads(contents)
        return json.dumps(temp[0:limit])

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

    filepath = os.path.join(config['logs-directory'], "history.json")

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

        # save to logfile
        with open(status[shortname]['logfile'], "a") as logfile:
            logfile.write(line.decode('utf-8'))

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

    if branch == "master":
        return None

    # fallback to master
    return imagefrom(client, repository, "master")



#
# build status
#
def buildsuccess(shortname):
    status[shortname]['status'] = 'success'
    status[shortname]['ended'] = int(time.time())
    history_push(shortname)

    # update github statues
    github_statues(status[shortname]['commit'], "success", status[shortname]['repository'])

    del status[shortname]

    return "OK"

def builderror(shortname, message):
    print("[-] %s: %s" % (shortname, message))

    status[shortname]['status'] = 'error'
    status[shortname]['error'] = message
    status[shortname]['ended'] = int(time.time())
    history_push(shortname)

    # update github statues
    github_statues(status[shortname]['commit'], "error", status[shortname]['repository'])

    del status[shortname]

    return "FAILED"

#
# Extract the kernel from a container
# if release is True, kernel is compiled from initramfs
# otherwise it's compiled from a core change
#
def kernel(shortname, tmpdir, branch, reponame, commit, release):
    # format kernel "zero-os-BRANCH-generic.efi" if it's a release
    suffix = 'generic-%s' % commit if release else "%s-%s" % (reponame, commit)
    kname = "zero-os-%s-%s.efi" % (branch, suffix)

    print("[+] exporting kernel: %s" % kname)

    # now we have the kernel on our tmpdir
    # let's copy it to the right location
    krnl = os.path.join(tmpdir.name, "vmlinuz.efi")
    dest = os.path.join(config['kernel-directory'], kname)

    if not os.path.isfile(krnl):
        return False

    print("[+] moving kernel into production")
    shutil.move(krnl, dest)

    basename = "zero-os-%s.efi" % branch if not release else "zero-os-%s-generic.efi" % branch
    target = os.path.join(config['kernel-directory'], basename)

    if os.path.islink(target) or os.path.isfile(target):
        os.remove(target)

    # moving to kernel directory
    now = os.getcwd()
    os.chdir(config['kernel-directory'])

    # symlink last kernel to basename
    os.symlink(kname, basename)
    os.chdir(now)

    status[shortname]['artifact'] = kname

    return True

#
# Github statues
#
def github_statues(commit, status, fullrepo):
    # skipping if no token provided
    if config["github-token"] == "":
        print("[-] no github token configured")
        return

    base = "https://api.github.com"
    headers = {"Authorization": "token " + config["github-token"]}

    data = {
        "state": status,
        "target_url": "%s/report/%s" % (config['public-host'], commit),
        "description": buildstatus[status],
        "context": "gig-autobuilder"
    }

    endpoint = "%s/repos/%s/statuses/%s" % (base, fullrepo, commit)
    print("[+] set status to: %s" % endpoint)

    req = requests.post(endpoint, headers=headers, json=data)
    print(req.json())

#
# Build workflow
#
class BuildThread(threading.Thread):
    def __init__(self, shortname, baseimage, repository, script, branch, reponame, commit, release):
        threading.Thread.__init__(self)

        self.shortname = shortname
        self.baseimage = baseimage
        self.repository = repository
        self.script = script
        self.branch = branch
        self.reponame = reponame
        self.commit = commit
        self.release = release

    def run(self):
        # connecting docker
        client = docker.from_env()

        # creating temporary workspace
        tmpdir = tempfile.TemporaryDirectory(prefix="initramfs-", dir=config['temp-directory'])
        print("[+] temporary directory: %s" % tmpdir.name)

        #
        # This is a main project, we build it
        # then make a base image from it
        #
        print("[+] starting container")
        volumes = {tmpdir.name: {'bind': '/target', 'mode': 'rw'}}
        target = client.containers.run(self.baseimage, tty=True, detach=True, volumes=volumes)

        status[self.shortname]['status'] = 'initializing'
        status[self.shortname]['docker'] = target.id

        # update github statues
        github_statues(status[self.shortname]['commit'], "pending", status[self.shortname]['repository'])

        if self.release:
            notice(self.shortname, 'Preparing system')
            execute(self.shortname, target, "apt-get update")
            execute(self.shortname, target, "apt-get install -y git")

            notice(self.shortname, 'Cloning repository')
            execute(self.shortname, target, "git clone -b '%s' https://github.com/%s" % (self.branch, self.repository))

        notice(self.shortname, 'Executing script')
        status[self.shortname]['status'] = 'building'

        try:
            # FIXME: should not happen
            if not self.release:
                execute(self.shortname, target, "sh -c 'cd /0-initramfs && git pull'")

            # compiling
            command = "bash /0-initramfs/autobuild/%s %s %s" % (self.script, self.branch, "0-initramfs")
            execute(self.shortname, target, command)

            if not os.path.isfile(os.path.join(tmpdir.name, "vmlinuz.efi")):
                raise RuntimeError("Kernel not found on %s/vmlinuz.efi" % tmpdir.name)

            # extract kernel
            kernel(self.shortname, tmpdir, self.branch, self.reponame, self.commit, self.release)

            if self.release:
                # commit to baseimage
                status[self.shortname]['status'] = 'committing'
                target.commit(self.repository, self.branch)

            # build well done
            buildsuccess(self.shortname)

        except Exception as e:
            traceback.print_exc()
            builderror(self.shortname, str(e))

        # end of build process
        target.remove(force=True)
        tmpdir.cleanup()

        return "OK"

def build(shortname, baseimage, repository, script, branch, reponame, commit, release):
    builder = BuildThread(shortname, baseimage, repository, script, branch, reponame, commit, release)
    builder.start()

    return "STARTED"

#
# Events
#
def event_ping(payload):
    print("[+] repository: %s" % payload['repository']['full_name'])
    return "OK"

# this push event returns streaming contents
# to avoid timeout
def event_push(payload):
    if payload["deleted"] and len(payload['commits']) == 0:
        print("[-] this is deleting push, skipping")
        return "DELETED"

    # extracting data from payload
    repository = payload['repository']['full_name']
    ref = payload['ref']
    branch = os.path.basename(ref)
    shortname = "%s/%s" % (repository, branch)
    commit = payload['head_commit']['id'][0:8]

    # connecting docker
    client = docker.from_env()

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
        'repository': repository,
        'ended': None,
        'error': None,
        'commits': payload['commits'],
        'commit': payload['head_commit']['id'],
        'artifact': None,
        'logfile': os.path.join(config['logs-directory'], "commits", payload['head_commit']['id']),
    }

    # cleaning previous logfile if any
    if os.path.isfile(status[shortname]['logfile']):
        os.remove(status[shortname]['logfile'])

    #
    # This is a little bit hardcoded for our side
    #
    if repository == "zero-os/0-core":
        baseimage = imagefrom(client, "zero-os/0-initramfs", branch)
        if not baseimage:
            return builderror(shortname, 'No base image found for branch: %s' % branch)

        print("[+] base image found: %s" % baseimage.tags)
        return build(shortname, baseimage.id, repository, "gig-build-cores.sh", branch, reponame, commit, False)

    if repository == "zero-os/0-fs":
        baseimage = imagefrom(client, "zero-os/0-initramfs", branch)
        if not baseimage:
            return builderror(shortname, 'No base image found for branch: %s' % branch)

        print("[+] base image found: %s" % baseimage.tags)
        return build(shortname, baseimage.id, repository, "gig-build-g8ufs.sh", branch, reponame, commit, False)

    if repository == "g8os/initramfs-gig":
        baseimage = imagefrom(client, "zero-os/0-initramfs", branch)
        if not baseimage:
            return builderror(shortname, 'No base image found for branch: %s' % branch)

        print("[+] base image found: %s" % baseimage.tags)
        return build(shortname, baseimage.id, repository, "gig-build-extensions.sh", branch, reponame, commit, False)

    if repository == "zero-os/0-initramfs":
        return build(shortname, "ubuntu:16.04", repository, "gig-build.sh", branch, reponame, commit, True)

    builderror(shortname, "Unknown repository, we don't follow this one.")
    abort(404)



#
# Routing
#
@app.route('/logs/<project>/<name>/<branch>', methods=['GET'])
def global_logs(project, name, branch):
    collapse = "%s/%s/%s" % (project, name, branch)
    if not logs.get(collapse):
        abort(404)

    response = make_response(logs[collapse])
    response.headers["Content-Type"] = "text/plain"

    return response

@app.route('/report/<hash>', methods=['GET'])
def global_commit_logs(hash):
    logfile = os.path.join(config['logs-directory'], "commits", hash)

    if not os.path.isfile(logfile):
        abort(404)

    with open(logfile, "r") as f:
        contents = f.read()

    response = make_response(contents)
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

@app.route('/build/history/full', methods=['GET'])
def global_history_full():
    response = make_response(history_raw())
    response.headers["Content-Type"] = "application/json"

    return response

@app.route('/build/history', methods=['GET'])
def global_history():
    response = make_response(history_raw(25))
    response.headers["Content-Type"] = "application/json"

    return response

#
# Git Hook
#
@app.route('/build/<project>/hook', methods=['GET', 'POST'])
def build_hook(project):
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

#
# Monitor page
#
@app.route("/monitor/", strict_slashes=False)
def index():
    return render_template("index.html")

@app.route("/", strict_slashes=False)
def index_root():
    return render_template("index.html")

#
# flist
#
@app.route(config['monitor-update-endpoint'], methods=['GET', 'POST'])
def monitor_update():
    if not request.headers.get('X-Github-Event'):
        abort(400)

    payload = request.get_json()

    if request.headers['X-Github-Event'] == "ping":
        print("[+] update-endpoint: ping event for: %s" % payload["repository"]["full_name"])
        return "PONG"

    if request.headers['X-Github-Event'] == "push":
        print("[+] update-endpoint: push event")
        return monitor.update(payload)

    print("[-] unknown event: %s" % request.headers['X-Github-Event'])
    abort(400)

@app.route(config['repository-push-endpoint'], methods=['GET', 'POST'])
def monitor_push():
    if not request.headers.get('X-Github-Event'):
        abort(400)

    payload = request.get_json()

    if request.headers['X-Github-Event'] == "ping":
        print("[+] push-endpoint: ping event for: %s" % payload["repository"]["full_name"])
        return "PONG"

    if request.headers['X-Github-Event'] == "push":
        print("[+] push-endpoint: push event")
        return monitor.push(payload)

    print("[-] unknown event: %s" % request.headers['X-Github-Event'])
    abort(400)

print("[+] configuring flist-watcher")
monitor.initialize()
monitor.dump()
monitor.webhooks()

print("[+] starting webapp")
app.run(host=config['http-listen'], port=config['http-port'], debug=config['debug'], threaded=True, use_reloader=False)
