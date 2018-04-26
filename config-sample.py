#
# You should adapt this part to your usage
#
config = {
    # Github webhook secret (not used now)
    'token': "1234",

    'kernel-directory': '/tmp/kernels/',
    'binary-directory': '/tmp/binaries/',
    'logs-directory': '/tmp/build-logs',
    'temp-directory': None,

    # HTTP listening port
    'http-port': 5560,
    'http-listen': "0.0.0.0",

    # Public web url to reach the build system
    'public-host': "http://domain.tld",

    # Github token to update build statues
    'github-token': "",

    # GitHub flist-monitor configuration repository
    'configuration-repository': "user/config-repo",

    # Endpoint for configuration update event
    'monitor-update-endpoint': "/hook/monitor-update",

    # Endpoint for watch'd repository push event
    'repository-push-endpoint': "/hook/monitor-watch",

    # ZeroHub **refreshable** jwt-token
    'zerohub-token': '',

    # ZeroHub username acting upload (needs to belong to the jwt scope)
    'zerohub-username': '',

    # Enable debug or production mode
    'debug': True,

    # Websocket Redis Gateway server
    'redis-host': '127.0.0.1',
    'redis-port': 6379,

    # Websocket Gateway webserver
    'websocket-listen': '0.0.0.0',
    'websocket-port': 3333,
}
