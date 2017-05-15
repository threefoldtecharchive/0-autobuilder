#
# You should adapt this part to your usage
#
config = {
    # Github webhook secret (not used now)
    'TOKEN': "debugmode1234abcd",

    'KERNEL_TARGET': '/tmp/kernels/',
    'LOGS_DIRECTORY': '/tmp/build-logs',
    'TMP_DIRECTORY': None,

    # HTTP listening port
    'HTTP_PORT': 5560,

    # Public web url to reach the build system
    'PUBLIC_HOST': "http://your.host",

    # Github token to update build statues
    'GITHUB_TOKEN': "",

    # Enable debug or production mode
    'DEBUG': True,
}
