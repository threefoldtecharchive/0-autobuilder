import os
import tempfile
import subprocess
import time
import yaml
import requests

class AutobuilderFlistMonitor:
    def __init__(self, config):
        self.configtarget = config['configuration-repository']
        self.token = config['github-token']
        self.repositories = {}

        self.watch = {
            "monitor": config['public-host'] + config['monitor-update-endpoint'],
            "repository": config['public-host'] + config['repository-push-endpoint'],
        }

        print("[+] update endpoint: %s" % self.watch['monitor'])
        print("[+] push endpoint: %s" % self.watch['repository'])

    def initialize(self):
        """
        Initialize repositories to watch and ensure webhooks
        """
        repo = tempfile.TemporaryDirectory(prefix="autobuild-git-")

        # cloning monitoring repository to a temporary directory
        args = ['git', 'clone', 'https://github.com/' + self.configtarget, repo.name]
        subprocess.run(args)

        # parsing the repository contents
        for root, dirs, files in os.walk(repo.name):
            # skipping .git directory, we assume all other directories
            # are repositories to watch
            if ".git" in dirs:
                dirs.remove(".git")

            rootdir = root[len(repo.name) + 1:].split('/')
            if len(rootdir) != 2:
                continue

            pathname = '/'.join(rootdir)
            self.repositories[pathname] = self.parse(root, files)

    def parse(self, root, files):
        branches = {}

        for file in files:
            filepath = os.path.join(root, file)

            # removing .yaml extension
            branchname = file[:-5]

            # loading branch config
            branches[branchname] = yaml.load(open(filepath, 'r'))

        return branches

    def dump(self):
        """
        Dumps the content of the parsed and loaded repositories
        """
        print("[+] watching %d repositories:" % len(self.repositories))
        for repository, contents in self.repositories.items():
            print("[+]   %s (%d branches):" % (repository, len(contents)))

            for branch in contents:
                print("[+]     - %s" % branch)
                print("[+]       -> %s" % contents[branch])

    def webhooks(self, previously={}):
        """
        Ensure webhooks are all sets to forward push to the monitor
        """
        self.webhook_repository(self.configtarget, self.watch['monitor'])

        for repository in self.repositories:
            if previously.get(repository):
                print("[+] webhook: %s: already configured" % repository)
                continue

            print("[+] repository: %s, setting up webhook" % repository)
            self.webhook_repository(repository, self.watch['repository'])

        return True

    def webhook_repository(self, repository, target):
        """
        Check and update webhook of a repository if not set
        """
        print("[+] webhook: managing: %s" % repository)

        existing = self.github('/repos/%s/hooks' % repository)
        for hook in existing:
            if not hook['config'].get('url'):
                continue

            # checking if webhook is already set
            if hook['config']['url'] == target:
                print("[+] webhook: %s: already up-to-date" % repository)
                return True

        # no webhook matching our url found, adding it
        options = self.webhook_config(target)
        print(self.github('/repos/%s/hooks' % repository, options))

    def webhook_config(self, target):
        config = {
            "name": 'web',
            "active": True,
            "events": ["push"],
            "config": { "url": target, "content_type": "json" }
        }

        return config

    def github(self, endpoint, data=None):
        headers = {'Authorization': 'token %s' % self.token}

        if data:
            return requests.post('https://api.github.com' + endpoint, headers=headers, json=data).json()

        return requests.get('https://api.github.com' + endpoint, headers=headers).json()

    def push(self, payload):
        """
        Return actions to do for a received push, None will be return if this
        repository/branch is not monitored
        """
        if payload["deleted"] and len(payload['commits']) == 0:
            print("[-] this is deleting push, skipping")
            return "DELETED"

        # extracting data from payload
        repository = payload['repository']['full_name']
        print(repository)
        print(payload)
        return "OK"

    def update(self, payload):
        """

        """
        if payload["deleted"] and len(payload['commits']) == 0:
            print("[-] this is deleting push, skipping")
            return "DELETED"

        # extracting data from payload
        repository = payload['repository']['full_name']
        print(repository)

        if repository != self.configtarget:
            print("[-] wrong repository, received: %s, excepted: %s" % (repository, self.configtarget))
            return "DENIED"

        print("[+] webhook: reloading configuration")
        previously = self.repositories

        self.initialize()
        self.dump()
        self.webhooks(previously)

        return "OK"
