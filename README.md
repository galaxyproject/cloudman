## CloudMan

Cloud clusters for everyone.

### Overview

[CloudMan][1] is a cloud manager that orchestrates all of the steps required
to provision a complete cluster environment on a cloud infrastructure;
subsequently, it allows one to manage the infrastructure, all through a web 
browser. Although CloudMan can be used in any domain and for any purpose that
calls for a compute cluster, it is primarily used in the context of [Galaxy Cloud][4]
and [CloudBioLinux][5] and, along with the infrastructure, ensures a complete 
Next Generation Sequencing (NGS) analysis toolset is instantly available.
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

[1]: https://usecloudman.org/
[2]: https://github.com/pypa/virtualenv
[3]: https://bitbucket.org/galaxy/cloudman
[4]: http://www.nature.com/nbt/journal/v29/n11/full/nbt.2028.html
[5]: http://cloudbiolinux.org/
[6]: http://aws.amazon.com/ec2/
[7]: http://biocloudcentral.org/

## LICENSE

The code is freely available under the [MIT license][l1].

[l1]: http://www.opensource.org/licenses/mit-license.html

