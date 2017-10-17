import os
import tempfile
import subprocess
import time
import yaml
import requests
import threading
import docker
import traceback

class AutobuilderFlistThread(threading.Thread):
    def __init__(self, components, task):
        threading.Thread.__init__(self)

        self.root = components
        self.task = task

        self.shortname = task.get('name')
        self.branch = task.get('branch')
        self.repository = task.get('repository')
        self.recipe = {}

    def _flist_name(self, archives):
        targetname = "%s-%s-%s.tar.gz" % (self.repository, self.branch, self.task.get('commit')[0:10])
        targetname = targetname.replace('/', '-')

        return os.path.join(archives, targetname)

    def build(self, baseimage, buildscript, archives, artifact):
        # connecting docker
        client = docker.from_env()

        # creating temporary workspace
        tmpdir = tempfile.TemporaryDirectory(prefix="flist-build-", dir=self.root.config['temp-directory'])
        print("[+] temporary directory: %s" % tmpdir.name)

        print("[+] starting container")
        volumes = {tmpdir.name: {'bind': archives, 'mode': 'rw'}}
        target = client.containers.run(baseimage, tty=True, detach=True, volumes=volumes)

        self.task.set_status('initializing')
        self.task.set_docker(target.id)

        self.task.notice('Building artifact %s (%s)' % (artifact, archives))

        # update github statues
        self.task.pending()

        self.task.notice('Preparing system')
        self.task.execute(target, "apt-get update")
        self.task.execute(target, "apt-get install -y git")

        self.task.notice('Cloning repository')
        self.task.execute(target, "git clone -b '%s' https://github.com/%s" % (self.branch, self.repository))

        self.task.notice('Executing script')
        self.task.set_status('building')

        try:
            command = "bash %s/%s" % (os.path.basename(self.repository), buildscript)
            self.task.execute(target, command)

            artifactfile = os.path.join(tmpdir.name, artifact)

            if not os.path.isfile(artifactfile):
                raise RuntimeError("Artifact not found, build failed")

            # prepare hub-upload
            self.task.notice('Uploading artifact to the hub')

            # rename the artifact to versioned-name
            targetpath = self._flist_name(archives)
            os.rename(artifactfile, targetpath)

            # upload the file
            self.root.zerohub.refresh()
            self.root.zerohub.upload(targetpath)

            # build well done
            self.task.success()

        except Exception as e:
            traceback.print_exc()
            self.task.error(str(e))

        # end of build process
        target.remove(force=True)
        tmpdir.cleanup()

        return "OK"

    def run(self):
        for buildscript in self.recipe['buildscripts']:
            artifact = self.recipe[buildscript]['artifact']
            baseimage = self.recipe[buildscript].get('baseimage') or "ubuntu:16.04"
            archives = self.recipe[buildscript].get('archives') or "/target"

            print("[+] building script: %s" % buildscript)
            print("[+]  - artifact expected: %s" % artifact)
            print("[+]  - base image: %s" % baseimage)
            print("[+]  - archive directory: %s" % archives)

            self.build(baseimage, buildscript, archives, artifact)
