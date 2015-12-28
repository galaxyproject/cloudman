![CloudMan Logo](https://wiki.galaxyproject.org/Images/GalaxyLogos?action=AttachFile&do=get&target=cloudman-logo.png)

Easily create a [compute cluster][9] on top of a [cloud computing
infrastructure][11].

### Overview

[CloudMan][1] is a cloud manager that orchestrates all of the steps required to
provision a complete compute cluster environment on a cloud infrastructure;
subsequently, it allows one to manage the cluster, all through a web browser.
Although CloudMan can be used in any domain and for any purpose that calls for
a compute cluster, it is primarily used in the context of [Galaxy Cloud][4] and
[CloudBioLinux][5] and, along with the infrastructure, ensures a complete [Next
Generation Sequencing (NGS)][10] analysis toolkit is instantly available.
CloudMan is currently available on the [AWS EC2 cloud][6].

### Use

To instantiate a CloudMan cluster, simply visit [usegalaxy.org/cloudlaunch][7].
Alternatively, or if you want start an instance on one of the non-Amazon
clouds, visit [biocloudcentral.org][12].

### Local deployment
For basic testing and some development, [CloudMan][1] can be run locally.
Start by cloning [CloudMan source][3], installing [virtualenv][2], and adding
Python libraries required by CloudMan. Then, run it:

    $ cd <project root dir>
    $ git clone https://github.com/galaxyproject/cloudman
    $ virtualenv .
    $ source bin/activate
    $ pip install -r cloudman/requirements.txt
    $ sh cloudman/run.sh [--reload]

### Custom cloud deployment
If you would like to deploy CloudMan and all of its dependencies on a cloud
infrastructure where a public image does not already exist, take a look at
[CloudBioLinux][8] scripts (`cloudman` flavor in particular).

[1]: https://wiki.galaxyproject.org/CloudMan
[2]: https://github.com/pypa/virtualenv
[3]: https://github.com/galaxyproject/cloudman
[4]: http://www.nature.com/nbt/journal/v29/n11/full/nbt.2028.html
[5]: http://cloudbiolinux.org/
[6]: http://aws.amazon.com/ec2/
[7]: http://usegalaxy.org/cloudlaunch/
[8]: https://github.com/chapmanb/cloudbiolinux/tree/master/contrib/flavor/cloudman
[9]: http://en.wikipedia.org/wiki/Computer_cluster
[10]: http://en.wikipedia.org/wiki/DNA_sequencing
[11]: http://en.wikipedia.org/wiki/Cloud_computing
[12]: https://biocloudcentral.org/

## LICENSE

The code is freely available under the [MIT license][l1].

[l1]: http://www.opensource.org/licenses/mit-license.html

