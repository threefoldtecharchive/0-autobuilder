import os
import docker
import threading
from modules.initramfsworker import AutobuilderInitramfsThread

class AutobuilderInitramfs:
    """
    This class handle event and trigger builds for initramfs and core0
    project from zero-os repositories, they are custom-made
    """
    def __init__(self, components):
        self.root = components

        self.watching = [
            "threefoldtech/0-core",
            "threefoldtech/0-fs",
            "g8os/initramfs-gig",
            "threefoldtech/0-initramfs",
        ]

        # ensure kernel directory
        if not os.path.exists(self.root.config['kernel-directory']):
            os.mkdir(self.root.config['kernel-directory'])

    def imagefrom(self, client, repository, branch):
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

    def build(self, task, baseimage, script, release):
        """
        Start a new build-thread
        We use threads to avoid time-out in webhook side, as soon as the build
        is authorized, we confirm the reception
        """
        builder = AutobuilderInitramfsThread(task, baseimage, script, release, self.root)
        builder.start()

        return "STARTED"


    def event_ping(self, payload):
        """
        Handle ping event from github webhook
        """
        print("[+] repository: %s" % payload['repository']['full_name'])
        return "OK"

    def event_push(self, payload):
        """
        Handle 'push' event from github webhook
        Mainly, this is where a build is triggered
        """
        if payload["deleted"] and len(payload['commits']) == 0:
            print("[-] this is deleting push, skipping")
            return "DELETED"

        task = self.root.buildio.create()
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
        if task.get('repository') == "threefoldtech/0-core":
            baseimage = self.imagefrom(client, "threefoldtech/0-initramfs", task.get('branch'))
            if not baseimage:
                task.error('No base image found for branch: %s' % task.get('branch'))
                task.destroy()
                return

            print("[+] base image found: %s" % baseimage.tags)
            return self.build(task, baseimage, "gig-build-cores.sh", False)

        if task.get('repository') == "threefoldtech/0-fs":
            baseimage = self.imagefrom(client, "threefoldtech/0-initramfs", task.get('branch'))
            if not baseimage:
                task.error('No base image found for branch: %s' % task.get('branch'))
                task.destroy()
                return

            print("[+] base image found: %s" % baseimage.tags)
            return self.build(task, baseimage, "gig-build-g8ufs.sh", False)

        if task.get('repository') == "g8os/initramfs-gig":
            baseimage = self.imagefrom(client, "threefoldtech/0-initramfs", task.get('branch'))
            if not baseimage:
                task.error('No base image found for branch: %s' % task.get('branch'))
                task.destroy()
                return

            print("[+] base image found: %s" % baseimage.tags)
            return self.build(task, baseimage, "gig-build-extensions.sh", False)

        if task.get('repository') == "threefoldtech/0-initramfs":
            return self.build(task, "ubuntu:16.04", "gig-build.sh", True)

        task.error("Unknown kernel repository, we don't follow this one.")
        task.destroy()
        abort(404)

    def webhooks(self):
        """
        Auto-configure watching repositories for webhook
        """
        for repository in self.watching:
            print("[+] repository: %s, setting up webhook" % repository)
            target = self.root.config['public-host'] + '/hook/kernel'
            self.webhook_repository(repository, target)

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
