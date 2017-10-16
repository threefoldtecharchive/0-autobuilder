import os
import json
import docker
import uuid
import time
import collections

class BuildIO:
    def __init__(self, config, github):
        self.config = config
        self.github = github

        self.status = {}

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
        filepath = os.path.join(self.config['logs-directory'], "history.json")

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
            'name': id,
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

        filepath = os.path.join(config['logs-directory'], "history.json")

        with open(filepath, "w") as f:
            f.write(json.dumps(history))

    """
    Build entry
    """
    def create(self):
        id = uuid.uuid4()

        entry = {
            'docker': "",
            'status': 'creating',
            'console': collections.deque(maxlen=20),
            'started': int(time.time()),
            'repository': repository,
            'ended': None,
            'error': None,
            'commits': [],
            'commit': None,
            'artifact': None,
            'logfile': os.path.join(self.config['logs-directory'], "commits", id),
        }

        self.status[id] = entry
        return BuildIOTask(self, id)

    def get(self, id):
        return self.status.get(id)

    """
    Build Status
    """
    def finish(self, id, status, message):
        print("[-] %s: %s" % (id, message))

        self.status[id]['status'] = status
        self.status[id]['ended'] = int(time.time())

        if message:
            self.status[id]['error'] = message

        # saving object in the history
        self.push(id)

        # update github statues
        self.github.statues(self.status[id]['commit'], status, self.status[id]['repository'])

        # removing object from running state
        del self.status[id]

    """
    Build output
    """
    def notice(id, message):
        """
        Add a simple notice message on the output build process
        """
        self.status[id]['console'].append("\n>>> %s\n" % message)

    def execute(id, target, command):
        """
        Execute a command inside docker container and track output
        """
        dockid = target.id[0:10]

        for line in target.exec_run(command, stream=True, stderr=True):
            # debug to console
            print("[%s] %s" % (dockid, line.strip().decode('utf-8')))

            # append to status
            self.status[id]['console'].append(line.decode('utf-8'))
            # logs[shortname] += line.decode('utf-8')

            # save to logfile
            with open(self.status[id]['logfile'], "a") as logfile:
                logfile.write(line.decode('utf-8'))

class BuildIOTask:
    def __init__(self, buildio, id):
        self.buildio = buildio
        self.taskid = id

    def set_repository(self, repository):
        self.buildio.status[self.taskid]['repository'] = repository

    def set_artifact(self, artifact):
        self.buildio.status[self.taskid]['artifact'] = artifact

    def set_status(self, status):
        self.buildio.status[self.taskid]['status'] = status

    def set_commit(self, commitid):
        self.buildio.status[self.taskid]['commit'] = commitid

    def set_commits(self, commits):
        self.buildio.status[self.taskid]['commits'] = commits

    def set_docker(self, dockerid):
        self.buildio.status[self.taskid]['docker'] = dockerid

    def notice(self, message):
        return self.buildio.notice(self.taskid, message)

    def success(self):
        """
        Finish a build with success state
        """
        self.buildio.finish(self.taskid, 'success', None)
        return "OK"

    def error(self, message):
        """
        Finish a build in error state
        """
        self.buildio.finish(self.taskid, 'error', message)
        return "FAILED"
