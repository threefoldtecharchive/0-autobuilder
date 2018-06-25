import os
import tempfile
import shutil
import docker
import traceback
import threading

class AutobuilderInitramfsThread(threading.Thread):
    """
    This class handle the build-thread kernel

    Workflow:
     - start a container with git support
     - clone the repository
     - execute the argument buildscript
     - extract kernel from container
     - move kernel to kernel directory
    """
    def __init__(self, task, baseimage, script, release, components):
        threading.Thread.__init__(self)

        if type(baseimage) is str:
            # string image
            self.baseimagename = baseimage
            self.baseimage = baseimage

        else:
            # docker image object
            self.baseimagename = baseimage.tags[0]
            self.baseimage = baseimage.id

        self.task = task
        self.shortname = task.get('name')
        self.repository = task.get('repository')
        self.script = script
        self.branch = task.get('branch')
        self.reponame = os.path.basename(task.get('repository'))
        self.commit = task.get('commit')[0:10]
        self.release = release
        self.root = components

    def images_cleaner(self, client):
        images = client.images.list()

        for image in images:
            if image.attrs['RepoTags'][0] == '<none>:<none>':
                print("[+] cleaner: removing image: %s" % image.id)
                client.images.remove(image.id)

    def kernel(self, tmpsource):
        """
        Extract the kernel from a container
         - if release is True, kernel is compiled from initramfs
         - otherwise it's compiled from a core change
        """
        # format kernel "zero-os-BRANCH-generic.efi" if it's a release
        suffix = 'generic-%s' % self.commit if self.release else "%s-%s" % (self.reponame, self.commit)
        kname = "zero-os-%s-%s.efi" % (self.branch, suffix)

        print("[+] exporting kernel: %s" % kname)

        # now we have the kernel on our tmpdir
        # let's copy it to the right location
        krnl = os.path.join(tmpsource, "vmlinuz.efi")
        dest = os.path.join(self.root.config['kernel-directory'], kname)

        if not os.path.isfile(krnl):
            return False

        print("[+] moving kernel into production")
        shutil.move(krnl, dest)

        basename = "zero-os-%s.efi" % self.branch if not self.release else "zero-os-%s-generic.efi" % self.branch
        target = os.path.join(self.root.config['kernel-directory'], basename)

        if os.path.islink(target) or os.path.isfile(target):
            os.remove(target)

        # moving to kernel directory
        now = os.getcwd()
        os.chdir(self.root.config['kernel-directory'])

        # symlink last kernel to basename
        os.symlink(kname, basename)
        os.chdir(now)

        self.task.set_artifact("kernel/%s" % kname)

        return True

    def run(self):
        # connecting docker
        client = docker.from_env()

        # creating temporary workspace
        tmpdir = tempfile.TemporaryDirectory(prefix="initramfs-", dir=self.root.config['temp-directory'])
        print("[+] temporary directory: %s" % tmpdir.name)

        print("[+] starting container")
        self.task.set_baseimage(self.baseimagename)

        extra_hosts = {'download.gig.tech': '172.17.0.1'}
        volumes = {tmpdir.name: {'bind': '/target', 'mode': 'rw'}}
        target = client.containers.run(self.baseimage, tty=True, detach=True, volumes=volumes, extra_hosts=extra_hosts)

        self.task.set_status('initializing')
        self.task.set_docker(target.id)

        self.task.pending()

        if self.release:
            self.task.notice('Preparing system')
            self.task.execute(target, "apt-get update")
            self.task.execute(target, "apt-get install -y git")

            self.task.notice('Cloning repository')
            self.task.execute(target, "git clone -b '%s' https://github.com/%s" % (self.branch, self.repository))

        self.task.notice('Executing script')
        self.task.set_status('building')

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
            self.kernel(tmpdir.name)

            if self.release:
                # commit to baseimage
                self.task.set_status('committing')
                target.commit(self.repository, self.branch)

            # build well done
            self.task.success()
            self.task.destroy()

        except Exception as e:
            traceback.print_exc()
            self.task.error(str(e))
            self.task.destroy()

        # end of build process
        target.remove(force=True)
        tmpdir.cleanup()

        # cleanup docker images
        self.images_cleaner(client)

        return "OK"
