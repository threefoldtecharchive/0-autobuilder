import os
import sys
import shutil
import time
import tempfile
import shutil
import docker
import collections
import tarfile
import json
import traceback
import requests
import threading
from subprocess import call

class AutobuilderInitramfs:
    def __init__(self, components):
        self.root = components

    def imagefrom(client, repository, branch):
        for image in client.images.list():
            if len(image.tags) == 0:
                continue

            # checking if we have a tag which start with the branch
            temp = image.tags[0].split(':')
            name = temp[0]
            tag  = temp[1]

            # this image have nothing to do with this repo
            if name != repository:
                continue

            # this image is not the right version
            if branch.startswith(tag):
                return image

        if branch == "master":
            return None

        # fallback to master
        return imagefrom(client, repository, "master")

    #
    # Extract the kernel from a container
    # if release is True, kernel is compiled from initramfs
    # otherwise it's compiled from a core change
    #
    def kernel(shortname, tmpdir, branch, reponame, commit, release):
        # format kernel "zero-os-BRANCH-generic.efi" if it's a release
        suffix = 'generic-%s' % commit if release else "%s-%s" % (reponame, commit)
        kname = "zero-os-%s-%s.efi" % (branch, suffix)

        print("[+] exporting kernel: %s" % kname)

        # now we have the kernel on our tmpdir
        # let's copy it to the right location
        krnl = os.path.join(tmpdir.name, "vmlinuz.efi")
        dest = os.path.join(components.config['kernel-directory'], kname)

        if not os.path.isfile(krnl):
            return False

        print("[+] moving kernel into production")
        shutil.move(krnl, dest)

        basename = "zero-os-%s.efi" % branch if not release else "zero-os-%s-generic.efi" % branch
        target = os.path.join(components.config['kernel-directory'], basename)

        if os.path.islink(target) or os.path.isfile(target):
            os.remove(target)

        # moving to kernel directory
        now = os.getcwd()
        os.chdir(components.config['kernel-directory'])

        # symlink last kernel to basename
        os.symlink(kname, basename)
        os.chdir(now)

        status[shortname]['artifact'] = kname

        return True

    #
    # Build workflow
    #
    class BuildThread(threading.Thread):
        def __init__(self, task, shortname, baseimage, repository, script, branch, reponame, commit, release, components):
            threading.Thread.__init__(self)

            self.task = task
            self.shortname = shortname
            self.baseimage = baseimage
            self.repository = repository
            self.script = script
            self.branch = branch
            self.reponame = reponame
            self.commit = commit
            self.release = release
            self.root = components

        def run(self):
            # connecting docker
            client = docker.from_env()

            # creating temporary workspace
            tmpdir = tempfile.TemporaryDirectory(prefix="initramfs-", dir=self.config['temp-directory'])
            print("[+] temporary directory: %s" % tmpdir.name)

            #
            # This is a main project, we build it
            # then make a base image from it
            #
            print("[+] starting container")
            volumes = {tmpdir.name: {'bind': '/target', 'mode': 'rw'}}
            target = client.containers.run(self.baseimage, tty=True, detach=True, volumes=volumes)

            self.task.set_status('initializing')
            self.task.set_docker(target.id)

            # update github statues
            # self.buildio.github.statues(status[self.shortname]['commit'], "pending", status[self.shortname]['repository'])
            # --> self.buildio.pending(taskid)

            if self.release:
                self.task.notice('Preparing system')
                self.task.execute(target, "apt-get update")
                self.task.execute(target, "apt-get install -y git")

                self.task.notice('Cloning repository')
                self.task.execute(target, "git clone -b '%s' https://github.com/%s" % (self.branch, self.repository))

            self.root.buildio.notice('Executing script')
            self.root.buildio.set_status('building')

            try:
                # FIXME: should not happen
                if not self.release:
                    self.task.execute(target, "sh -c 'cd /0-initramfs && git pull'")

                # compiling
                command = "bash /0-initramfs/autobuild/%s %s %s" % (self.script, self.branch, "0-initramfs")
                self.task.execute(target, command)

                if not os.path.isfile(os.path.join(tmpdir.name, "vmlinuz.efi")):
                    raise RuntimeError("Kernel not found on %s/vmlinuz.efi" % tmpdir.name)

                # extract kernel
                kernel(self.shortname, tmpdir, self.branch, self.reponame, self.commit, self.release)

                if self.release:
                    # commit to baseimage
                    self.task.set_status('committing')
                    target.commit(self.repository, self.branch)

                # build well done
                self.task.success()

            except Exception as e:
                traceback.print_exc()
                self.task.error(str(e))

            # end of build process
            target.remove(force=True)
            tmpdir.cleanup()

            return "OK"

    def build(task, shortname, baseimage, repository, script, branch, reponame, commit, release):
        builder = BuildThread(task, shortname, baseimage, repository, script, branch, reponame, commit, release, components)
        builder.start()

        return "STARTED"

    #
    # Events
    #
    def event_ping(payload):
        print("[+] repository: %s" % payload['repository']['full_name'])
        return "OK"

    # this push event returns streaming contents
    # to avoid timeout
    def event_push(payload):
        if payload["deleted"] and len(payload['commits']) == 0:
            print("[-] this is deleting push, skipping")
            return "DELETED"

        task = components.buildio.create()
        task.set_from_push(payload)

        """
        # extracting data from payload
        repository = payload['repository']['full_name']
        ref = payload['ref']
        branch = os.path.basename(ref)
        shortname = "%s/%s" % (repository, branch)
        commit = payload['head_commit']['id'][0:8]
        reponame = os.path.basename(repository)
        """

        # connecting docker
        client = docker.from_env()

        print("[+] repository: %s, branch: %s" % (task.get('repository'), task.get('branch')))

        # checking for existing tasks
        """
        FIXME FIXME FIXME

        if buildio.status.get(shortname):
            if status[shortname]['status'] not in ['success', 'error']:
                print("[-] task already running, ignoring")
                return "BUSY"
        """

        """
        # creating entry for that build

        task.set_repository(repository)
        task.set_commit(payload['head_commit']['id'])
        task.set_commits(payload['commits'])
        task.set_status('preparing')
        """

        # cleaning previous logfile if any
        '''
        if os.path.isfile(status[shortname]['logfile']):
            os.remove(status[shortname]['logfile'])
        '''

        #
        # This is a little bit hardcoded for our side
        #
        if repository == "zero-os/0-core":
            baseimage = imagefrom(client, "zero-os/0-initramfs", task.get('branch'))
            if not baseimage:
                return task.error('No base image found for branch: %s' % task.get('branch'))

            print("[+] base image found: %s" % baseimage.tags)
            return build(task, baseimage.id, "gig-build-cores.sh", False)

        if repository == "zero-os/0-fs":
            baseimage = imagefrom(client, "zero-os/0-initramfs", task.get('branch'))
            if not baseimage:
                return task.error('No base image found for branch: %s' % task.get('branch'))

            print("[+] base image found: %s" % baseimage.tags)
            return build(task, baseimage.id, "gig-build-g8ufs.sh", False)

        if repository == "g8os/initramfs-gig":
            baseimage = imagefrom(client, "zero-os/0-initramfs", task.get('branch'))
            if not baseimage:
                return task.error('No base image found for branch: %s' % task.get('branch'))

            print("[+] base image found: %s" % baseimage.tags)
            return build(task, baseimage.id, "gig-build-extensions.sh", False)

        if repository == "zero-os/0-initramfs":
            return build(task, "ubuntu:16.04", "gig-build.sh", True)

        task.error("Unknown repository, we don't follow this one.")
        abort(404)
