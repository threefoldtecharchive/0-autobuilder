from config import config
from modules.flist import AutobuilderFlistMonitor
from modules.github import AutobuilderGitHub
from modules.zerohub import ZeroHubClient
from modules.buildio import BuildIO
from modules.initramfs import AutobuilderInitramfs
from modules.webapp import AutobuilderWebApp

class AutobuilderComponents:
    def __init__(self, config):
        print("[+] initializing components")
        self.config = config

        print("[+] loading module: flask-webapp")
        self.webapp = AutobuilderWebApp(self)

        print("[+] loading module: github")
        self.github = AutobuilderGitHub(self)

        print("[+] loading module: buildio")
        self.buildio = BuildIO(self)

        print("[+] loading module: flist-autobuilder")
        self.monitor = AutobuilderFlistMonitor(self)

        print("[+] loading module: zerohub")
        self.zerohub = ZeroHubClient(self)

        print("[+] loading module: initramfs")
        self.initram = AutobuilderInitramfs(self)

if __name__ == '__main__':
    app = AutobuilderComponents(config)

    print("[+] configuring: flist-watcher")
    app.monitor.initialize()
    app.monitor.dump()
    app.monitor.webhooks()
    app.initram.webhooks()

    print("[+] configuring: webapp")
    app.webapp.routes()

    print("[+] starting webserver")
    app.webapp.serve()
