### CloudMan - November 26, 2012.

* Support for Eucalyptus cloud middleware. Thanks to [Alex Richter][11].
  Also, CloudMan can now run on the [HPcloud][12] in basic mode.

* Added a new file system management interface on the Admin page, allowing
  control and providing insight into each available file system

* Added quite a few new user data options. See the [UserData][6] page for
  details. Thanks to [John Chilton][13].

* Galaxy can now be run in multi-process mode. Thanks to [John Chilton][13].

* Added Galaxy Reports app as a CloudMan service. Thanks to [John Chilton][13].

* Introduced a new format for cluster configuration persistence, allowing
  more flexibility in how services are maintained

* Added a new file system service for instance's transient storage, allowing
  it to be used across the cluster over NFS. The file system is available at
  ``/mnt/transient_nfs`` just know that any data stored there **will not be
  preserved** after a cluster is terminated.

* Support for Ubuntu 12.10

* Worker instances are now also SGE submit hosts

* New log file format and improved in-code documentation

* Many, many more smaller enhancements and bug fixes. For a complete list of
  changes, see the [175 commit messages][14].

### CloudMan - June 8, 2012.

* Support for OpenStack and OpenNebula cloud middleware, allowing easy
  deployment on private, OpenStack or OpenNebula based, clouds (see
  [CloudBioLinux][1] and [mi-deployment][2] projects for an easy way to deploy
  CloudMan on any machine image).

* Start your instances via [biocloudcentral.org][3] on any supported cloud by
  simply filling out a 4-field web form. See [this screencast][7] for an example
  of using it with the Australian National Research Cloud, NeCTAR.

* Support for [Amazon Spot instances][4], giving you an opportunity to reduce
  cost of running your cluster on AWS.

* Ability to mount any S3 bucket as a local file system via the Admin page,
  giving you instant and easy file-based access to any of your buckets or
  public buckets, such as the [1000genomes][5] one.

* Added the ability to disable running of jobs on the master instance (via the
  Admin page), allowing you to (1) run a smaller instance type longer for the
  same cost and (2) not see the responsiveness of the master instance degrade
  with jobs being submitted.

* Significantly enhanced the details pane for individual worker nodes on the
  main interface, including much better responsiveness and added support for
  terminating and restarting individual nodes.

* Added MPI and SMP parallel environments to SGE; do `qconf -spl` to see
  the list and `qsub -pe <pe_name> <slots>` to use it for your cluster jobs.

* Removal of data volumes now happens in parallel, shortening the cluster
  shutdown time.

* Added *worker_post_start_script_url* and *share_string* user data options.
  See the [User Data wiki page][6] for the complete list.

* Added a messaging framework to allow system information to easily and
  prominently be shown on the main interface. For example, if an instance
  was restarted in the wrong zone for its data volume - an explicit message
  will be shown indicating there was an error and what should be done.

* Support for Ubuntu 12.04

* Enhancements to logging by progressively reducing the frequency of log
  output as no user interaction takes place and also introduced log rotation.

* For a complete list of changes, see the 112 [commit messages][8] since the
  last release.


[1]: http://cloudbiolinux.org/
[2]: https://bitbucket.org/afgane/mi-deployment/
[3]: http://biocloudcentral.org/
[4]: http://aws.amazon.com/ec2/spot-instances/
[5]: http://aws.amazon.com/datasets/4383
[6]: http://wiki.g2.bx.psu.edu/CloudMan/UserData
[7]: http://www.youtube.com/watch?v=AKu_CbbgEj0
[8]: https://bitbucket.org/galaxy/cloudman/changesets/tip/151%3Af13145c3221e
[9]: https://bitbucket.org/site/master/issue/2288/parse-render-restructuredtext-markdown
[10]: http://github.github.com/github-flavored-markdown/preview.html
[11]: https://bitbucket.org/razrichter
[12]: https://www.hpcloud.com/
[13]: https://bitbucket.org/jmchilton
[14]: https://bitbucket.org/galaxy/cloudman/changesets/tip/3a63b9a40331%3A35baec1
