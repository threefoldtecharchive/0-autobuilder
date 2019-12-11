import docker
import time
import dateutil.parser
from datetime import datetime, timezone
from config import config

class AutobuilderMaintenance():
    def __init__(self):
        print("[+] initializing docker")
        self.docker = docker.from_env()

    def run(self):
        containers = self.docker.containers.list()
        now = datetime.now(timezone.utc)

        for container in containers:
            if not container.name.startswith(config['flist-autobuilder-prefix']):
                # print("[+] container: skipping: %s" % container.name)
                continue

            if not container.attrs['State']['Running']:
                print("[+] container: %s: not running" % container.name)
                continue

            initdate = container.attrs['State']['StartedAt']
            init = dateutil.parser.parse(initdate)

            diff = now - init
            minutes = int(diff.total_seconds() / 60)

            print("[+] container: %s is running for %d minutes" % (container.name, minutes))

            if minutes < config['maximum-execution-time']:
                print("[+] container: can keep going: %s" % container.name)
                continue

            print("[+] container: maximum execution time reached, killing: %s" % container.name)
            container.remove(force=True)

    def forever(self):
        while True:
            self.run()
            time.sleep(10)


if __name__ == '__main__':
    maintenance = AutobuilderMaintenance()
    maintenance.forever()
