import requests

class ZeroHubClient:
    """
    This class interact with the Zero-OS Hub (hub.gig.tech) to upload and manage
    files, we use itsyou.online authentification tokens

    To make this working on long-time, please provide a refreshable jwt token from
    itsyou.online, moreover the username your provide needs to be your username
    or a username part of user:memberof:xxxx scope, otherwise upload will fails
    """
    def __init__(self, components):
        self.root = components

        self.token = self.root.config['zerohub-token']
        self.user = self.root.config['zerohub-username']

        self.baseurl = 'https://hub.gig.tech'
        self.baseiyo = 'https://itsyou.online'

        self.cookies = {
            'caddyoauth': self.token,
            'active-user': self.user
        }

    def upload(self, filename):
        """
        Upload a local file to the hub
        """
        files = {'file': open(filename,'rb')}
        r = requests.post('%s/api/flist/me/upload' % self.baseurl, files=files, cookies=self.cookies)
        response = r.json()

        if response['status'] != 'success':
            print(response)
            return False

        return True

    def refresh(self):
        """
        Refresh a itsyou.online refreshable jwt token
        """
        headers = {'Authorization': 'bearer %s' % self.token}

        response = requests.get('%s/v1/oauth/jwt/refresh' % self.baseiyo, headers=headers)
        self.token = response.text
        self.cookies['caddyoauth'] = self.token

    def symlink(self, linkname, target):
        """
        Create a symlink on the hub
        """
        endpoint = '%s/api/flist/me/%s/link/%s' % (self.baseurl, target, linkname)
        r = requests.get(endpoint, cookies=self.cookies)
        response = r.json()

        if response['status'] != 'success':
            print(response)
            return False

        return True
