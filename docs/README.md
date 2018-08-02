# Zero-OS Auto Builder

Automatic Zero-OS kernel builds are triggered when commits happen in the following GitHub repositories:

- [threefoldtech/0-core](https://github.com/threefoldtech/0-core)
- [threefoldtech/0-fs](https://github.com/threefoldtech/0-fs)
- [threefoldtech/0-initramfs](https://github.com/threefoldtech/0-initramfs)

The build process can be monitored here: https://build.gig.tech/monitor/.

The result is shown on the home page of the [Zero-OS Bootstrap Service](https://bootstrap.gig.tech/), see the [threefoldtech/0-bootstrap](https://github.com/threefoldtech/0-bootstrap) repository for more details.

Each time a commit is pushed to GitHub, a build request is called:
- If you push to `threefoldtech/0-initramfs`, a complete kernel image will be rebuilt, which can take up to **1 hour**
- If you push to `threefoldtech/0-core` or `threefoldtech/0-fs`, a pre-compiled `initramfs` image (called `baseimage`) will be used, the actual build of `core0` or `0-fs` only takes **about 3 minutes**

In order to have a **3 minutes** compilation time for cores, the build process uses a pre-compiled `initramfs` image (called `baseimage`). If no base image is found, the build will be ignored.

## Base image and branches

When you push to `0-initramfs`, a base image will be produced automatically at the end of the build. This base image will be tagged with the branch name. E.g. if you push to `1.1.0-alpha`, the base image will be called `1.1.0-alpha`.

When you push to `core0` or `0-fs`, a base image will be looked up that matches the branch-prefix. E.g. when pushing a commit to the `1.1.0-alpha-issue-155` the build process will use the base image `1.1.0-alpha`. In theory a base image for each of the branches should exist.

So you always **NEED** to prefix your branch with the name of an existing base image. If you would push a commit to `mybranch` instead of `1.1.0-alpha-mybranch` (forgetting/omitting the prefix), the build will not occur, and an error will be raised.
