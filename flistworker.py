import os
import tempfile
import subprocess
import time
import yaml
import requests
import threading
import docker

class AutobuilderFlistThread(threading.Thread):
    def __init__(self, config, github):
        threading.Thread.__init__(self)

        self.config = config
        self.github = github

        self.baseimage = "ubuntu:16.04"
        self.shortname = "flist-debug"
        self.branch = "master"
        self.repository = "maxux/hooktest"
        self.command = "autobuild/gig-flist-build.sh"

    def run(self):
        status = {self.shortname: {}}

        # connecting docker
        client = docker.from_env()

        # creating temporary workspace
        tmpdir = tempfile.TemporaryDirectory(prefix="flist-build-", dir=self.config['temp-directory'])
        print("[+] temporary directory: %s" % tmpdir.name)

        print("[+] starting container")
        volumes = {tmpdir.name: {'bind': '/tmp/archive', 'mode': 'rw'}}
        target = client.containers.run(self.baseimage, tty=True, detach=True, volumes=volumes)

        status[self.shortname]['status'] = 'initializing'
        status[self.shortname]['docker'] = target.id

        # update github statues
        # github_statues(status[self.shortname]['commit'], "pending", status[self.shortname]['repository'])

        notice(self.shortname, 'Preparing system')
        execute(self.shortname, target, "apt-get update")
        execute(self.shortname, target, "apt-get install -y git")

        notice(self.shortname, 'Cloning repository')
        execute(self.shortname, target, "git clone -b '%s' https://github.com/%s" % (self.branch, self.repository))

        notice(self.shortname, 'Executing script')
        status[self.shortname]['status'] = 'building'

        command = "bash %s/%s" % (os.path.basename(self.repository), self.command)
        execute(self.shortname, target, command)

        """
        if not os.path.isfile(os.path.join(tmpdir.name, "vmlinuz.efi")):
            raise RuntimeError("Kernel not found on %s/vmlinuz.efi" % tmpdir.name)
        """

        # build well done
        # buildsuccess(self.shortname)

        """
        except Exception as e:
            traceback.print_exc()
            builderror(self.shortname, str(e))
        """

        # end of build process
        target.remove(force=True)
        tmpdir.cleanup()

        return "OK"
