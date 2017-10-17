import os
import json
import docker
import uuid
import time
import collections

class BuildIO:
    def __init__(self, components):
        self.root = components

        self.status = {}

        # ensure logs directories
        if not os.path.exists(self.root.config['logs-directory']):
            os.mkdir(self.root.config['logs-directory'])

        sublogfiles = os.path.join(self.root.config['logs-directory'], "commits")
        if not os.path.exists(sublogfiles):
            os.mkdir(sublogfiles)

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
            'name': self.status[id]['name'],
            'status': self.status[id]['status'],
            'monitor': empty.join(self.status[id]['console']),
            'docker': self.status[id]['docker'][0:10],
            'started': self.status[id]['started'],
            'ended': self.status[id]['ended'],
            'error': self.status[id]['error'],
            'commits': self.status[id]['commits'],
            'artifact': self.status[id]['artifact'],
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
            'branch': None,
            'logfile': os.path.join(self.root.config['logs-directory'], "commits", id),
        }

        self.status[id] = entry
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

        # removing object from running state
        del self.status[id]

    """
    Build output
    """
    def notice(self, id, message):
        """
        Add a simple notice message on the output build process
        """
        self.status[id]['console'].append("\n>>> %s\n" % message)

        with open(self.status[id]['logfile'], "a") as logfile:
            logfile.write("\n>>> %s\n" % message)

    def execute(self, id, target, command):
        """
        Execute a command inside docker container and track output
        """
        dockid = target.id[0:10]

        for line in target.exec_run(command, stream=True, stderr=True):
            # debug to console
            print("[%s] %s" % (dockid, line.strip().decode('utf-8')))

            # append to status
            self.status[id]['console'].append(line.decode('utf-8'))

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

    def set_repository(self, repository):
        self.root.buildio.status[self.taskid]['repository'] = repository

    def set_artifact(self, artifact):
        self.root.buildio.status[self.taskid]['artifact'] = artifact

    def set_status(self, status):
        self.root.buildio.status[self.taskid]['status'] = status

    def set_commit(self, commitid):
        self.root.buildio.status[self.taskid]['commit'] = commitid

    def set_commits(self, commits):
        self.root.buildio.status[self.taskid]['commits'] = commits

    def set_docker(self, dockerid):
        self.root.buildio.status[self.taskid]['docker'] = dockerid

    def set_name(self, name):
        self.root.buildio.status[self.taskid]['name'] = name

    def set_branch(self, branch):
        self.root.buildio.status[self.taskid]['branch'] = branch


    def set_from_push(self, payload):
        repository = payload['repository']['full_name']
        reponame = os.path.basename(repository)

        ref = payload['ref']
        branch = os.path.basename(ref)

        shortname = "%s/%s" % (repository, branch)
        shortcommit = payload['head_commit']['id'][0:8]

        self.set_repository(repository)
        self.set_commit(payload['head_commit']['id'])
        self.set_commits(payload['commits'])
        self.set_name(shortname)
        self.set_branch(branch)


    def get(self, key):
        return self.root.buildio.status[self.taskid].get(key)


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

    def pending(self):
        self.root.github.statuses(self.get('commit'), self.taskid, "pending", self.get('repository'))


    def execute(self, target, command):
        """
        Execute a command inside task'd docker container and track output
        """
        return self.root.buildio.execute(self.taskid, target, command)
