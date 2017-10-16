import os
import tempfile
import subprocess
import time
import yaml
import requests

class AutobuilderFlistThread(threading.Thread):
    def __init__(self, config, github):
        threading.Thread.__init__(self)

        self.config = config
        self.github = github

    def run(self):
        # connecting docker
        client = docker.from_env()

        """
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
        """
        return True
