import os
import tempfile
import threading
import docker
import traceback
import subprocess

class AutobuilderFlistThread(threading.Thread):
    """
    This class handle the build-thread flist

    Workflow:
     - start a container with git support
     - clone the repository
     - for each buildscripts configured:
       - execute this buildscript
       - upload the artifact on the hub
    """
    def __init__(self, components, task):
        threading.Thread.__init__(self)

        self.root = components
        self.task = task

        self.shortname = task.get('name')
        self.branch = task.get('branch')
        self.repository = task.get('repository')
        self.recipe = {}

        self.default_baseimage = self.root.monitor.default_baseimage
        self.default_archives = self.root.monitor.default_archives

    def _flist_generic(self):
        temp = "%s-%s.flist" % (self.repository, self.branch)
        return temp.replace('/', '-')

    def _flist_endname(self):
        temp = "%s-%s-%s.flist" % (self.repository, self.branch, self.task.get('commit')[0:10])
        return temp.replace('/', '-')

    def _flist_targz(self):
        temp = "%s-%s-%s.tar.gz" % (self.repository, self.branch, self.task.get('commit')[0:10])
        return temp.replace('/', '-')

    def _flist_name(self, archives):
        return os.path.join(archives, self._flist_targz())

    def build(self, baseimage, buildscript, archives, artifact):
        # connecting docker
        client = docker.from_env()

        # creating temporary workspace
        tmpdir = tempfile.TemporaryDirectory(prefix="flist-build-", dir=self.root.config['temp-directory'])
        print("[+] temporary directory: %s" % tmpdir.name)

        tmpgit = tempfile.TemporaryDirectory(prefix="git-source-", dir=self.root.config['temp-directory'])
        print("[+] temporary git source directory: %s" % tmpdir.name)

        subprocess.call(["git", "clone", "-b", self.branch, "https://github.com/%s" % self.repository, tmpgit.name])

        print("[+] starting container")
        volumes = {
            tmpdir.name: {'bind': archives, 'mode': 'rw'},
            tmpgit.name: {'bind': '/%s' % os.path.basename(self.repository), 'mode': 'rw'},
        }

        target = client.containers.run(baseimage, tty=True, detach=True, volumes=volumes)

        self.task.set_status('initializing')
        self.task.set_docker(target.id)

        self.task.notice('Building artifact %s (%s)' % (artifact, archives))

        # update github statues
        self.task.pending()

        self.task.notice('Preparing system')
        # self.task.execute(target, "apt-get update")
        # self.task.execute(target, "apt-get install -y git")

        self.task.notice('Cloning repository')
        # self.task.execute(target, "git clone -b '%s' https://github.com/%s" % (self.branch, self.repository))

        self.task.notice('Executing script')
        self.task.set_status('building')

        try:
            command = "chmod +x /%s/%s" % (os.path.basename(self.repository), buildscript)
            self.task.execute(target, command)

            command = "/%s/%s" % (os.path.basename(self.repository), buildscript)
            self.task.execute(target, command)

            artifactfile = os.path.join(tmpdir.name, artifact)

            if not os.path.isfile(artifactfile):
                raise RuntimeError("Artifact not found, build failed")

            # prepare hub-upload
            self.task.notice('Uploading artifact to the hub')

            # rename the artifact to versioned-name
            targetpath = os.path.join(tmpdir.name, self._flist_targz())
            os.rename(artifactfile, targetpath)

            # upload the file
            print("[+] refreshing jwt")
            self.root.zerohub.refresh()

            print("[+] uploading file")
            self.root.zerohub.upload(targetpath)

            print("[+] updating symlink")
            self.root.zerohub.symlink(self._flist_generic(), self._flist_endname())

            # build well done
            self.task.success()

        except Exception as e:
            traceback.print_exc()
            self.task.error(str(e))

        # end of build process
        target.remove(force=True)
        tmpdir.cleanup()
        tmpgit.cleanup()

        return "OK"

    def run(self):
        for buildscript in self.recipe['buildscripts']:
            artifact = self.recipe[buildscript]['artifact']
            baseimage = self.recipe[buildscript].get('baseimage') or self.default_baseimage
            archives = self.recipe[buildscript].get('archives') or self.default_archives

            print("[+] building script: %s" % buildscript)
            print("[+]  - artifact expected: %s" % artifact)
            print("[+]  - base image: %s" % baseimage)
            print("[+]  - archive directory: %s" % archives)

            self.build(baseimage, buildscript, archives, artifact)
