# Zero-OS Auto Builder
This webservice is a build-process (like Jenkins/Travis) tuned for Zero-OS internal development

## What does it do
### Kernel
This service autobuild a kernel when someone push on theses repositories:
- `threefoldtech/0-initramfs`
- `threefoldtech/0-core`
- `threefoldtech/0-fs`

Theses repo have github's webhook configured to trigger on push.

When a push is received, some actions are donc depending of the repository.

### Flist
This service autobuild flists based on user-defined configuration repository

The reposity provided in configuration will be auto-set to trigger push to this webservice.
This allows hot-reload when pushing into configuration.

Each directories are one organization/username to watch, and subdirectories are repositories.
Each subdirectory need to contains `branchname.yaml` file. This file looks like this:

```
buildscripts:
  - autobuild/gig-flist-build-1.sh
  - autobuild/gig-flist-build-2.sh

autobuild/gig-flist-build-1.sh:
  archives: /tmp/archives
  artifact: result.tar.gz

autobuild/gig-flist-build-2.sh:
  baseimage: ubuntu:14.04
  archives: /tmp/archives
  artifact: result.tar.gz
  tag: special-tag
```

You need at least one `buildscripts` entry, which contains a list of build-scripts.

Each buildscript needs to be defined and accepts following keys:
- archives: **(needed)** provide path where to find artifact
- artifact: **(needed)** provide filename of the final archive
- baseimage: image to use on the container, default is `ubuntu:16.04`
- tag: a special tag added to the build name

As soon as something is pushed to a tracked `branchname`, the build scripts are executed and artifacts
are uploaded to the hub.

## Actions
When a push is received from `zero-os/initramfs`:
- A new docker based on fresh `ubuntu:16.04` is started and a complete initramfs build is done
- When build is done, kernel is extracted and copied to `bootstrap` [zero-os/bootstrap]
- A docker image is created (commit) and tagged with the branch as name

When a push is received from `zero-os/core0` or `zero-os/g8ufs`:
- A new docker based on `initramfs/[base-branch]` is started and only cores and 0-FS are rebuild
- When build is done, kernel is extracted and copied to `bootstrap` [zero-os/bootstrap]

## Configuration
You can configure the service via `config.py`.

> Please copy `config-sample.py`, and configure it, information is inside this file.

You need to specify webhook to point to this webserice, the endpoint is: `/build/[project]/hook`. `[project]` is an arbitrary name.

## Neasted Docker
This service use Docker to build targets, it needs a working docker. If you are already running this
service in a docker, you'll need to gives access to host's docker (via volume or tcp).

To get the artifacts from the docker, a mount volume (temporary directory) is used to achieve this. Of course
if you are on a container already, the root of your container is not the same root as the host, the temporary directory
will be created on the host and not on your container, to fix this issue, you need to configure `TMP_DIRECTORY` to
points to a shared directory between container and host.

## Monitor
### Web Interface
The endpoint `/monitor` will shows you in realtime what's currently going on and previous build process.

The realtime logs are sent via websocket, as soon as the line is received in the python client.

In order to proceed websocket correctly, this process is not run in the main web server.
A redis-topic is used to communicate between server and websocket-server.

You can reach some logs and specific build status with:
- `/build/history`
- `/build/status`
- `/build/logs/<project>/<name>/<branch>`

### GitHub Statuses
Moreover, webservice will update github statuses according to the build process.
Status like **success**, **error** and **pending** will be forwarded to GitHub and full-logs url
will be dispatched as well. You can use this service to authorize Pull Requests only on success build.

### Configuration parser
When then autobuilder starts or the configuration repository is modified, during parsing of the
configuration files, the parsing is logged like any build and status is reported to github as well.
You can easily knows some configuration files was malformed, etc.

# Warning
Then initramfs are build, all images with empty tag and repository name are removed.

Then rebuilding a lot of image, this leak a lot of unused space. Be careful to tag your images
if you want to keep them.

# Documentation
For more documentation see the [`/docs`](./docs) directory, where you'll find a [table of contents](/docs/SUMMARY.md).
