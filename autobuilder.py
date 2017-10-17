import os
from config import config
from modules.flist import AutobuilderFlistMonitor
from modules.github import AutobuilderGitHub
from modules.zerohub import ZeroHubClient
from modules.buildio import BuildIO
from modules.initramfs import AutobuilderInitramfs
from modules.webapp import AutobuilderWebApp

class AutobuilderComponents:
    def __init__(self, config):
        print("[+] initializing empty components")

        self.config = config

        self.webapp = None
        self.github = None
        self.initram = None
        self.zerohub = None
        self.buildio = None
        self.monitor = None
        self.flist = None

if __name__ == '__main__':
    app = AutobuilderComponents(config)

    print("[+] loading module: flask-webapp")
    app.webapp = AutobuilderWebApp(app)

    print("[+] loading module: github")
    app.github = AutobuilderGitHub(app)

    print("[+] loading module: buildio")
    app.buildio = BuildIO(app)

    print("[+] loading module: flist-autobuilder")
    app.monitor = AutobuilderFlistMonitor(app)

    print("[+] loading module: zerohub")
    app.zerohub = ZeroHubClient(app)


    print("[+] configuring: flist-watcher")
    app.monitor.initialize()
    app.monitor.dump()
    app.monitor.webhooks()

    print("[+] configuring: webapp")
    app.webapp.routes()

    print("[+] starting webserver")
    app.webapp.serve()
