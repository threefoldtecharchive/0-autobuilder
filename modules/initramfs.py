import docker
import threading
from modules.initramfsworker import AutobuilderInitramfsThread

class AutobuilderInitramfs:
    def __init__(self, components):
        self.root = components

    def imagefrom(client, repository, branch):
        """
        Search for a valid base image, based on branch name
        """
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
        return self.imagefrom(client, repository, "master")

    #
    # Build workflow
    #
    def build(task, baseimage, script, release):
        builder = AutobuilderInitramfsThread(task, baseimage, script, release, self.root)
        builder.start()

        return "STARTED"

    #
    # Events
    #
    def event_ping(self, payload):
        """
        Handle ping event from github webhook
        """
        print("[+] repository: %s" % payload['repository']['full_name'])
        return "OK"

    # this push event returns streaming contents
    # to avoid timeout
    def event_push(self, payload):
        """
        Handle 'push' event from github webhook
        Mainly, this is where a build is triggered
        """
        if payload["deleted"] and len(payload['commits']) == 0:
            print("[-] this is deleting push, skipping")
            return "DELETED"

        task = components.buildio.create()
        task.set_from_push(payload)

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

        # This is a little bit hardcoded for our side
        if repository == "zero-os/0-core":
            baseimage = self.imagefrom(client, "zero-os/0-initramfs", task.get('branch'))
            if not baseimage:
                return task.error('No base image found for branch: %s' % task.get('branch'))

            print("[+] base image found: %s" % baseimage.tags)
            return self.build(task, baseimage.id, "gig-build-cores.sh", False)

        if repository == "zero-os/0-fs":
            baseimage = self.imagefrom(client, "zero-os/0-initramfs", task.get('branch'))
            if not baseimage:
                return task.error('No base image found for branch: %s' % task.get('branch'))

            print("[+] base image found: %s" % baseimage.tags)
            return self.build(task, baseimage.id, "gig-build-g8ufs.sh", False)

        if repository == "g8os/initramfs-gig":
            baseimage = self.imagefrom(client, "zero-os/0-initramfs", task.get('branch'))
            if not baseimage:
                return task.error('No base image found for branch: %s' % task.get('branch'))

            print("[+] base image found: %s" % baseimage.tags)
            return self.build(task, baseimage.id, "gig-build-extensions.sh", False)

        if repository == "zero-os/0-initramfs":
            return self.build(task, "ubuntu:16.04", "gig-build.sh", True)

        task.error("Unknown kernel repository, we don't follow this one.")
        abort(404)
