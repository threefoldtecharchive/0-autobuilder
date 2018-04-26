import os
import tempfile
import subprocess
import yaml
from modules.flistworker import AutobuilderFlistThread

class AutobuilderFlistMonitor:
    """
    This class takes care of the flist-webhooks and monitor any changes

    Workflow:
     # Initialization
     - clone configuration repository
     - parse contents (directories are repositories, files are branch settings)

     # Set webhook endpoints itself

     # When a push is receive on the configuration repository
     - re-clone this repository and re-parse the contents
     - update local configuration

     # When a push is receive to a flist-hook
     - start a container with git support
     - check if the push event is related to a monitored repository and branch
     - if we support this push, starting a flist-build-thread
    """
    def __init__(self, components):
        self.root = components
        self.configtarget = self.root.config['configuration-repository']

        self.repositories = {}
        self.compiled = True

        self.watch = {
            "monitor": self.root.config['public-host'] + self.root.config['monitor-update-endpoint'],
            "repository": self.root.config['public-host'] + self.root.config['repository-push-endpoint'],
        }

        self.default_baseimage = "ubuntu:16.04"
        self.default_archives = "/target"

        print("[+] update endpoint: %s" % self.watch['monitor'])
        print("[+] push endpoint: %s" % self.watch['repository'])

    def current_revision(self, path):
        previous = os.getcwd()
        os.chdir(path)

        commitid = subprocess.run(['git', 'rev-parse', 'HEAD'], stdout=subprocess.PIPE)
        os.chdir(previous)

        return commitid.stdout.decode('utf-8').strip()

    def initialize(self):
        """
        Initialize repositories to watch and ensure webhooks
        """
        repo = tempfile.TemporaryDirectory(prefix="autobuild-git-")

        # initializing error flag
        self.compiled = True

        # cloning monitoring repository to a temporary directory
        args = ['git', 'clone', 'https://github.com/' + self.configtarget, repo.name]
        subprocess.run(args)

        task = self.root.buildio.create()
        task.set_name('Configuration reloader')
        task.set_commit(self.current_revision(repo.name))
        task.set_repository(self.configtarget)
        task.set_docker('system')
        task.notice('Loading configuration')

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

            task.log('Parsing repository: %s' % pathname)
            self.repositories[pathname] = self.parse(root, files, task)

        if not self.compiled:
            task.notice("Configuration loaded, with some errors")
            task.error("Some configuration files could not be parsed correctly")
            task.destroy()
            return False

        task.notice("Configuration loaded without any errors")
        task.success()
        task.destroy()

    def _yaml_validate(self, contents, task):
        if not contents.get('buildscripts'):
            print("[-] WARNING: buildscripts not defined, skipping")
            task.log("Error: buildscripts not defined, ignoring this branch")
            return False

        for buildscript in contents['buildscripts']:
            if not contents.get(buildscript):
                print("[-] WARNING: buildscript '%s' not defined" % buildscript)
                task.log("ERROR: buildscript '%s' not defined, ignoring this branch" % buildscript)
                return False

            if not contents[buildscript].get('artifact'):
                print("[-] WARNING: buildscripts '%s' have no artifact")
                task.log("Error: buildscript '%s' have no artifact, ignoring this branch" % buildscript)
                return False

        return True

    def parse(self, root, files, task):
        branches = {}

        for file in files:
            filepath = os.path.join(root, file)

            # removing .yaml extension
            branchname = file[:-5]

            # loading branch config
            contents = yaml.load(open(filepath, 'r'))

            if not self._yaml_validate(contents, task):
                self.compiled = False
                continue

            task.log("Tracking branch: %s" % branchname)
            branches[branchname] = contents

        return branches

    def dump(self):
        """
        Dumps the content of the parsed and loaded repositories
        """
        print("[+] watching %d repositories:" % len(self.repositories))
        print("[+]")

        for repository, contents in self.repositories.items():
            print("[+]   %s (%d branches):" % (repository, len(contents)))

            for branch in contents:
                print("[+]     - %s" % branch)

                for buildscript in contents[branch]['buildscripts']:
                    buildinfo = contents[branch][buildscript]
                    print("[+]     +--> %s:" % buildscript)
                    print("[+]          artifact : %s" % buildinfo['artifact'])
                    print("[+]          baseimage: %s" % buildinfo.get('baseimage') or self.default_baseimage)
                    print("[+]          archives : %s" % buildinfo.get('archives') or self.default_archives)
                    print("[+]          extra tag: %s" % buildinfo.get('tag') or '(none)')

            print("[+]")

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

        existing = self.root.github.request('/repos/%s/hooks' % repository)
        for hook in existing:
            if not hook['config'].get('url'):
                continue

            # checking if webhook is already set
            if hook['config']['url'] == target:
                print("[+] webhook: %s: already up-to-date" % repository)
                return True

        # no webhook matching our url found, adding it
        options = self.root.github.webhook(target)
        print(self.root.github.request('/repos/%s/hooks' % repository, options))

    def push(self, payload):
        """
        Method triggered when a push-event is send to a monitored repository
        Basicly, this method will trigger a build (and do the most useful job)
        """
        if payload["deleted"] and len(payload['commits']) == 0:
            print("[-] this is deleting push, skipping")
            return {'status': 'success'}

        # extracting data from payload
        repository = payload['repository']['full_name']
        if not self.repositories.get(repository):
            print("[-] push: %s: we don't monitor this repository" % repository)
            return {'status': 'error', 'message': 'repository not tracked'}

        ref = payload['ref']
        branch = os.path.basename(ref)

        if not self.repositories[repository].get(branch):
            print("[-] push: %s: we don't monitor this branch: %s" % (repository, branch))
            return {'status': 'error', 'message': 'branch not tracked'}

        print("[+] push: %s: build trigger accepted (branch: %s)" % (repository, branch))

        for buildscript in self.repositories[repository][branch]['buildscripts']:
            task = self.root.buildio.create()
            task.set_from_push(payload)

            recipe = self.repositories[repository][branch][buildscript]

            print("[+] instanciating: %s" % buildscript)
            worker = AutobuilderFlistThread(self.root, task, recipe, buildscript)
            worker.start()

        return {'status': 'success'}

    def update(self, payload):
        """
        Method triggered when a push is sent to the configuration-repository
        This method will do some security check then reload the configuration-repository
        and parse again the contents in order to be sync'd with upstream data
        """
        if payload["deleted"] and len(payload['commits']) == 0:
            print("[-] this is deleting push, skipping")
            return {'status': 'success'}

        # extracting data from payload
        repository = payload['repository']['full_name']
        print(repository)

        if repository != self.configtarget:
            print("[-] wrong repository, received: %s, excepted: %s" % (repository, self.configtarget))
            return {'status': 'error', 'message': 'repository not configured as configuration-repository'}

        print("[+] webhook: reloading configuration")
        previously = self.repositories.copy()

        self.initialize()
        self.dump()
        self.webhooks(previously)

        return {'status': 'success'}
