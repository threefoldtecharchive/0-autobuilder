import requests

class AutobuilderGitHub:
    def __init__(self, config):
        self.config = config
        self.token = config['github-token']

        self.buildstatus = {
            "success": "build succeed",
            "error": "build failed, please check report",
            "pending": "building...",
        }

    def request(self, endpoint, data=None):
        """
        Do a Github API request (GET or POST is data is not None, data will be sent as JSON)
        """
        if not self.token:
            print("[-] no github token configured")
            return

        headers = {'Authorization': 'token %s' % self.token}

        if data:
            return requests.post('https://api.github.com' + endpoint, headers=headers, json=data).json()

        return requests.get('https://api.github.com' + endpoint, headers=headers).json()

    def statuses(self, commit, status, fullrepo):
        """
        Report build status to github
        """
        data = {
            "state": status,
            "target_url": "%s/report/%s" % (self.config['public-host'], commit),
            "description": self.buildstatus[status],
            "context": "gig-autobuilder"
        }

        endpoint = "%s/repos/%s/statuses/%s" % (base, fullrepo, commit)
        print("[+] github: set status to: %s" % endpoint)

        print(self.request(endpoint, data))
