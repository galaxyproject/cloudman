## CloudMan

Easily create a [compute cluster][9] on top of a [cloud computing infrastructure][11].

### Overview

[CloudMan][1] is a cloud manager that orchestrates all of the steps required
to provision a complete compute cluster environment on a cloud infrastructure;
subsequently, it allows one to manage the cluster, all through a web 
browser. Although CloudMan can be used in any domain and for any purpose that
calls for a compute cluster, it is primarily used in the context of [Galaxy Cloud][4]
and [CloudBioLinux][5] and, along with the infrastructure, ensures a complete 
[Next Generation Sequencing (NGS)][10] analysis toolset is instantly available.
CloudMan is currently available on the [AWS EC2 cloud][6].

### Use

To instantiate a CloudMan cluster, simply visit [biocloudcentral.org][7].

### Local deployment
For basic testing and some development, [CloudMan][1] can be run locally.
Start by cloning [CloudMan source][3], installing [virtualenv][2], and
adding Python libraries required by CloudMan. Then, run it:

    $ cd <project root dir>
    $ hg clone https://bitbucket.org/galaxy/cloudman
    $ virtualenv --no-site-packages .
    $ source bin/activate
    $ pip install -r cloudman/requirements.txt
    $ sh cloudman/run.sh [--reload]

### Custom cloud deployment
If you would like to deploy CloudMan and all of its dependencies on a cloud
infrastructure where a public image does not already exist, take a look at
[mi-deployment][8] scripts (mi_fabfile.py in particular), which enable an easy
way to do so.

[1]: https://usecloudman.org/
[2]: https://github.com/pypa/virtualenv
[3]: https://bitbucket.org/galaxy/cloudman
[4]: http://www.nature.com/nbt/journal/v29/n11/full/nbt.2028.html
[5]: http://cloudbiolinux.org/
[6]: http://aws.amazon.com/ec2/
[7]: http://biocloudcentral.org/
[8]: https://bitbucket.org/afgane/mi-deployment/
[9]: http://en.wikipedia.org/wiki/Computer_cluster
[10]: http://en.wikipedia.org/wiki/DNA_sequencing
[11]: http://en.wikipedia.org/wiki/Cloud_computing

## LICENSE

The code is freely available under the [MIT license][l1].

[l1]: http://www.opensource.org/licenses/mit-license.html

