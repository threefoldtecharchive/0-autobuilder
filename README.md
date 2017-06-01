# Zero-OS Auto Builder
This webservice is a build-process (like Jenkins) tuned for g8os internal development

## What does it do
This service autobuild a kernel when someone push on theses repositories:
- `zero-os/initramfs`
- `zero-os/core0`
- `zero-os/g8ufs`

Theses repo have github's webhook configured to trigger on push.

When a push is received, some actions are donc depending of the repository.

## Actions
When a push is received from `zero-os/initramfs`:
- A new docker based on fresh `ubuntu:16.04` is started and a complete initramfs build is done
- When build is done, kernel is extracted and copied to `bootstrap` [zero-os/bootstrap]
- A docker image is created (commit) and tagged with the branch as name

When a push is received from `zero-os/core0` or `zero-os/g8ufs`:
- A new docker based on `initramfs/[base-branch]` is started and only cores and g8ufs are rebuild
- When build is done, kernel is extracted and copied to `bootstrap` [zero-os/bootstrap]

## Configuration
You can customize the service by editing `config.py`:
- `TOKEN`: token used to authorize webhook (not used yet)
- `KERNEL_TARGET`: path to store artifacts
- `LOGS_DIRECTORY`: path to store logs
- `TMP_DIRECTORY`: prefix for temp directories (`None` for system default), see Neasted Docker for more info
- `HTTP_PORT`: http listen port
- `DEBUG`: enable (True) or disable (False) Flask debug mode

You need to specify webhook to point to this webserice, the endpoint is: `/build/[project]/hook`. `[project]` is an arbitrary name.

## Neasted Docker
This service use Docker to build the kernels, it needs a working docker. If you are already running this
service in a docker, you'll need to gives access to host's docker (via volume or tcp).

To get the kernel from the docker, a mount volume (temporary directory) is used to achieve this. Of course
if you are on a container already, the root of your container is not the same root as the host, the temporary directory
will be created on the host and not on your container, to fix this issue, you need to configure `TMP_DIRECTORY` to a shared
directory between container and host.

## Monitor
The endpoint `/monitor` will shows you in (nearly) realtime what's currently going on and previous build process

You can reach some logs and specific build status with:
- `/build/history`
- `/build/status`
- `/build/logs/<project>/<name>/<branch>`

## Documentation

For more documentation see the [`/docs`](./docs) directory, where you'll find a [table of contents](/docs/SUMMARY.md).
