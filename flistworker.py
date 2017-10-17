import os
import tempfile
import subprocess
import time
import yaml
import requests
import threading
import docker

class AutobuilderFlistThread(threading.Thread):
    def __init__(self, components, task):
        threading.Thread.__init__(self)

        self.root = components
        self.task = task

        self.baseimage = "ubuntu:16.04"
        self.shortname = task.get('name')
        self.branch = task.get('branch')
        self.repository = task.get('repository')
        self.command = "autobuild/gig-flist-build.sh"

    def run(self):
        # connecting docker
        client = docker.from_env()

        # creating temporary workspace
        tmpdir = tempfile.TemporaryDirectory(prefix="flist-build-", dir=self.root.config['temp-directory'])
        print("[+] temporary directory: %s" % tmpdir.name)

        print("[+] starting container")
        volumes = {tmpdir.name: {'bind': '/tmp/archive', 'mode': 'rw'}}
        target = client.containers.run(self.baseimage, tty=True, detach=True, volumes=volumes)

        self.task.set_status('initializing')
        self.task.set_docker(target.id)

        # update github statues
        self.task.pending()

        self.task.notice('Preparing system')
        self.task.execute(target, "apt-get update")
        self.task.execute(target, "apt-get install -y git")

        self.task.notice('Cloning repository')
        self.task.execute(target, "git clone -b '%s' https://github.com/%s" % (self.branch, self.repository))

        self.task.notice('Executing script')
        self.task.set_status('building')

        command = "bash %s/%s" % (os.path.basename(self.repository), self.command)
        self.task.execute(target, command)

        """
        if not os.path.isfile(os.path.join(tmpdir.name, "vmlinuz.efi")):
            raise RuntimeError("Kernel not found on %s/vmlinuz.efi" % tmpdir.name)
        """

        # build well done
        self.task.success()

        """
        except Exception as e:
            traceback.print_exc()
            builderror(self.shortname, str(e))
        """

        # upload artifact to zero-hub


        # end of build process
        target.remove(force=True)
        tmpdir.cleanup()

        return "OK"
