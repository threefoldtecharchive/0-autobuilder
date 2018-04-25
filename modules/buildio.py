import os
import json
import docker
import uuid
import time
import collections
import redis

class BuildIO:
    """
    This class will handle all Input/Output request to a build (a task)
    This one is the top-level abstraction of status monitoring and persistance
    Please use a Task (see below) to handle them more efficiently
    """
    def __init__(self, components):
        self.root = components

        print("[+] buildio: connecting redis dispatching")
        self.redis = redis.Redis(self.root.config['redis-host'], self.root.config['redis-port'])

        self.status = {}
        self.live_history()

        # ensure logs directories
        if not os.path.exists(self.root.config['logs-directory']):
            os.mkdir(self.root.config['logs-directory'])

        sublogfiles = os.path.join(self.root.config['logs-directory'], "commits")
        if not os.path.exists(sublogfiles):
            os.mkdir(sublogfiles)

    """
    Live updater
    """
    def live_current(self, notify=True):
        output = {}
        empty = ""

        for key, item in self.status.items():
            output[key] = {
                'status': item['status'],
                'name': item['name'],
                'monitor': empty.join(item['console']),
                'docker': item['docker'][0:10],
                'started': item['started'],
                'ended': item['ended'],
                'error': item['error'],
                'commits': item['commits'],
                'artifact': item['artifact'],
                'tag': item['tag'],
                'baseimage': item['baseimage'],
            }

        channel = "autobuilder-current" if notify else "autobuilder-current-update"
        self.redis.publish(channel, json.dumps(output))

    def live_history(self):
        history = self.raw(25)
        self.redis.publish("autobuilder-history", history)

    def live_update(self, id, line):
        self.redis.publish("autobuilder-update", json.dumps({'id': id, 'line': line}))
        self.live_current(False)

    """
    Build history
    """
    def backlog(self, limit=None):
        """
        Returns json object of the backlog, with optional limits
        """
        return json.loads(self.raw(limit))

    def raw(self, limit=None):
        """
        Returns raw text object of the backlog, with optional limits
        """
        filepath = os.path.join(self.root.config['logs-directory'], "history.json")

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

    def commit(self, id):
        """
        Insert entry to the raw backlog file
        """
        history = self.backlog()
        empty = ""

        item = {
            'id': id,
            'name': self.status[id]['name'],
            'status': self.status[id]['status'],
            'monitor': empty.join(self.status[id]['console']),
            'docker': self.status[id]['docker'][0:10],
            'started': self.status[id]['started'],
            'ended': self.status[id]['ended'],
            'error': self.status[id]['error'],
            'commits': self.status[id]['commits'],
            'artifact': self.status[id]['artifact'],
            'tag': self.status[id]['tag'],
            'payload': self.status[id]['payload'],
            'baseimage': self.status[id]['baseimage'],
        }

        history.insert(0, item)

        filepath = os.path.join(self.root.config['logs-directory'], "history.json")

        with open(filepath, "w") as f:
            f.write(json.dumps(history))

    """
    Build entry
    """
    def create(self):
        id = str(uuid.uuid4())

        entry = {
            'docker': '',
            'status': 'creating',
            'console': collections.deque(maxlen=20),
            'started': int(time.time()),
            'repository': None,
            'ended': None,
            'error': None,
            'commits': [],
            'commit': None,
            'artifact': None,
            'name': '',
            'branch': None,
            'logfile': os.path.join(self.root.config['logs-directory'], "commits", id),
            'tag': None,
            'baseimage': None,
            'payload': {},
        }

        self.status[id] = entry

        self.live_current()

        return BuildIOTask(self.root, id)

    def get(self, id):
        return self.status.get(id)

    """
    Build Status
    """
    def finish(self, id, status, message):
        self.status[id]['status'] = status
        self.status[id]['ended'] = int(time.time())

        if message:
            self.status[id]['error'] = message

        # saving object in the history
        self.commit(id)

        # update github statues
        entry = self.status[id]
        self.root.github.statuses(entry['commit'], id, status, entry['repository'])

        # update live history
        self.live_history()
        self.live_current()

    def destroy(self, id):
        # removing object from running state
        del self.status[id]
        self.live_current()


    """
    Build output
    """
    def log(self, id, message):
        """
        Add a log entry in the output build process
        """
        message = message + "\n"
        self.status[id]['console'].append(message)

        with open(self.status[id]['logfile'], "a") as logfile:
            logfile.write(message)

    def notice(self, id, message):
        """
        Add a simple notice message on the output build process
        """
        return self.log(id, "\n>>> %s" % message)

    def execute(self, id, target, command):
        """
        Execute a command inside docker container and track output
        """
        dockid = target.id[0:10]

        for line in target.exec_run(command, stream=True, stderr=True):
            # debug to console
            print("[%s] %s" % (dockid, line.strip().decode('utf-8')))

            # append to status
            linestr = line.decode('utf-8')

            self.status[id]['console'].append(linestr)
            self.live_update(id, linestr)

            # save to logfile
            with open(self.status[id]['logfile'], "a") as logfile:
                logfile.write(line.decode('utf-8'))

class BuildIOTask:
    """
    Wrap BuildIO class with a specific task-id
    This class represent a task (a build request) and handle logs, executions, etc.
    """
    def __init__(self, components, id):
        self.root = components
        self.taskid = id

    def setter(self, item, value):
        self.root.buildio.status[self.taskid][item] = value
        self.root.buildio.live_current()

    def set_repository(self, repository):
        self.setter('repository', repository)

    def set_artifact(self, artifact):
        self.setter('artifact', artifact)

    def set_status(self, status):
        self.setter('status', status)

    def set_commit(self, commitid):
        self.setter('commit', commitid)

    def set_commits(self, commits):
        self.setter('commits', commits)

    def set_docker(self, dockerid):
        self.setter('docker', dockerid)

    def set_name(self, name):
        self.setter('name', name)

    def set_branch(self, branch):
        self.setter('branch', branch)

    def set_tag(self, tag):
        self.setter('tag', tag)

    def set_payload(self, payload):
        self.setter('payload', payload)

    def set_baseimage(self, baseimage):
        self.setter('baseimage', baseimage)

    def set_from_push(self, payload):
        repository = payload['repository']['full_name']
        reponame = os.path.basename(repository)

        ref = payload['ref']
        branch = os.path.basename(ref)

        shortname = "%s/%s" % (repository, branch)
        shortcommit = payload['head_commit']['id'][0:8]

        self.set_payload(payload)
        self.set_repository(repository)
        self.set_commit(payload['head_commit']['id'])
        self.set_commits(payload['commits'])
        self.set_name(shortname)
        self.set_branch(branch)


    def get(self, key):
        return self.root.buildio.status[self.taskid].get(key)


    def log(self, message):
        return self.root.buildio.log(self.taskid, message)

    def notice(self, message):
        return self.root.buildio.notice(self.taskid, message)


    def success(self):
        """
        Finish task-build with success state
        """
        print("[+] %s [success]" % self.taskid)
        self.root.buildio.finish(self.taskid, 'success', None)
        return "OK"

    def error(self, message):
        """
        Finish task-build in error state
        """
        print("[-] %s [error]: %s" % (self.taskid, message))
        self.root.buildio.finish(self.taskid, 'error', message)
        return "FAILED"

    def destroy(self):
        self.root.buildio.destroy(self.taskid)

    def pending(self):
        self.root.github.statuses(self.get('commit'), self.taskid, "pending", self.get('repository'))


    def execute(self, target, command):
        """
        Execute a command inside task'd docker container and track output
        """
        return self.root.buildio.execute(self.taskid, target, command)
