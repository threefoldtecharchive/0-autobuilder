import requests

class ZeroHubClient:
    def __init__(self, config):
        self.config = config

        self.token = config['zerohub-token']
        self.user = config['zerohub-username']

        self.baseurl = 'https://staging.hub.gig.tech'
        self.baseiyo = 'https://itsyou.online'

        self.cookies = {
            'caddyoauth': self.token,
            'active-user': self.user
        }

    def upload(self, filename):
        files = {'file': open(filename,'rb')}
        r = requests.post('%s/api/flist/me/upload' % self.baseurl, files=files, cookies=self.cookies)
        response = r.json()

        if response['status'] != 'success':
            print(response)
            return False

        return True

    def merge(self, sources, target):
        """
        arguments = []

        for source in sources:
            arguments.append(('flists[]', source))

        arguments.append(('name', target))
        r = requests.post('%s/merge' % self.baseurl, data=arguments, cookies=self.cookies)
        print(r.text)

        return True
        """
        pass

    def refresh(self):
        """
        Refresh a itsyou.online refreshable jwt token
        """
        headers = {'Authorization': 'bearer %s' % self.token}

        self.token = requests.get('%s/v1/oauth/jwt/refresh' % self.baseiyo, headers=headers)
        self.cookies['caddyoauth'] = self.token
