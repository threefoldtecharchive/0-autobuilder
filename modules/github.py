import requests

class AutobuilderGitHub:
    """
    This class provide basic integration of github without extra dependencies
    This basicly only supports get/post api requests and build statuses updates

    Please provide a valid github api token on the config file
    """
    def __init__(self, components):
        self.root = components

        self.token = self.root.config['github-token']
        self.baseurl = "https://api.github.com"

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
            return requests.post(self.baseurl + endpoint, headers=headers, json=data).json()

        r = requests.get(self.baseurl + endpoint, headers=headers)
        try:
            return r.json()

        except Exception as e:
            print(e)
            print(r.text)
            return {}

    def statuses(self, commit, taskid, status, fullrepo):
        """
        Report build status to github
        """
        data = {
            "state": status,
            "target_url": "%s/report/%s" % (self.root.config['public-host'], taskid),
            "description": self.buildstatus[status],
            "context": "gig-autobuilder"
        }

        endpoint = "/repos/" + fullrepo + "/statuses/" + commit
        print("[+] github: set status to: %s" % endpoint)

        print(self.request(endpoint, data))

    def webhook(self, target):
        """
        Generate a json ready to use to configure github-webhook using
        target as endpoint url
        """
        config = {
            "name": 'web',
            "active": True,
            "events": ["push"],
            "config": {"url": target, "content_type": "json"}
        }

        return config
