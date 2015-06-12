### CloudMan - August 6, 2014.

* On AWS, updated galaxyFS snapshot (`snap-e6e1c04a`), which includes the June 2, 2014 Galaxy release with the July 30th security fix. All the tools installed via the Tool Shed have been updated and a number of new tools added, most notably: Tophat2, Bowtie2, FastQC, several FASTQ manipulation tools, several QC tools.

* For AWS, added support for VPC

* For OpenStack clouds, added the ability to automatically recover worker instances on cluster reboot

* Added support for creating a file system based on a downloadable archive

* Do not run Galaxy with multiple processes by default. This is because Tool Shed installs do not work properly in the multi-process mode. This feature can be enabled by setting user data optionconfigure_multiple_galaxy_processes to True when launching an instance.

* Set SGE slots in each queue to be equal to the number of cores on the instance

* Set instance IP in the Galaxy's FTP data upload tool message

* Added support for Nginx v1.4 and allow it (with the PAM module) to used as the authentication mechanism when accessing Galaxy Reports app

* Fixed cluster deletion when performed via the API

* No longer automatically start Hadoop and HTCondor services
On manually-invoked instance reboots, do not increment the instance reboot count that otherwise eventually leads to instance termination

* Limit the size of the log message buffer used in the UI to 1000 lines. Long-running instances had issues with this log growing large and that led to poor UI performance. The complete log is still available from the Admin page (or the command line).

* Automatically delete the bucket/container for Test type (ie, 'SGE only') clusters on cluster termination


### CloudMan - January 7, 2014.

##### Major updates
* On AWS, updated *galaxy* (snap-69893175) and *galaxyIndices* (snap-4b20f451)
  file system snapshots, which include the Nov 4, 2013 Galaxy release as well as
  a significant number of Galaxy tools updates and additions. Tool installations
  from the Tool Shed work as expected.

* Updated the AWS AMI: *Galaxy CloudMan 2.3* (ami-a7dbf6ce)

* Made multi-process Galaxy the default option for running Galaxy with CloudMan.

* Automatically toggle master as job execution host or not when workers are present.

* Added support for attaching external Gluster based filesystems + the ability
  to init clusters off gluster/nfs volumes when so configured in *snaps.yaml*.

* Added support for creating a volume based on an *archive_url* allowing a file
  system to be downloaded at cluster launch; also made it possible to use transient
  disk for this.

* Added tagging support for OpenStack instances (requires OpenStack Havana release).

* Galaxy Reports app now starts by default on Galaxy type clusters; it is accessible
  on ``<instance IP>/reports/`` URL.

##### Minor updates

* Added AWS new High I/O instance types.

* Created *proFTPd* service for managing the application; fixes occasional issues
  with FTP connectivity

* Updated *admin_users* (in Admin) form data-prefill and explanatory text to
  indicate correctly that this form now sets all admin users, instead of appending
  to the existing list.

* Included cluster name into the page title.

* Explicitly indicate that upon cluster deletion shared clusters get removed too.

* Added ``TMPDIR`` env var to point to a dir on (Galaxy's) data file system.

* Generalize support for finding ``libc`` on newer Ubuntu platforms. Allows CloudMan
  to run on Ubuntu 13.04 and tries to be future compatible with new minor releases
  of ``libc`` (thanks Brad Chapman).

* Numerous fixes, see commit log for details.


### CloudMan - June 29, 2013.

* Unification of ``galaxyTools`` and ``galaxyData`` file systems into a single
  ``galaxy`` filesystem. This file system is based on a common snapshot but
  following the initial volume creation, the volume remains as a permamanet
  part of the given cluster. This change makes it possible to utilize the
  [Galaxy Tool Shed][19] for installing tools into Galaxy.

* Due to the above file system unification, all existing clusters will need to
  go through a migration that performs the file system unification. This process
  has been automated via a newly developed *Migration Service*.

* For AWS, created a new base machine image (ami-118bfc78) and a new snapshot
  for the ``galaxy`` file system. This snapshot includes the current latest
  release of Galaxy and an updated set of tools.

* Added initial support for Hadoop-type workloads (see [this page][15] for more
  usage details and [this paper][18] more technical details)

* Added initial support for cluster federation via HTCondor (see [this page][16]
  for more usage details and [this paper][18] more technical details)

* Added a new file system service for instance's transient storage, allowing the
  transient storage to be used across the cluster over NFS as temporary data
  storage

* Added the ability to add an external NFS file system

* Added the ability to add an new-volume based file system

* Added the ability to add a file system from instance's local path (i.e., one
  that has been manually made avalable on an instance)

* Added support to persist a bucket-based file system between cluster invocations

* Added a service for the Galaxy Reports webapp

* Added support for [Loggly][17] based off-site logging; simply register
  on the site and provide your token (i.e., input key) as part of user data key
  ``cm_loggly_token``

* For AWS, added tags to spot instances (tags added after a Spot request is filled);
  added cluster name tag to any attached volume as well as any snapshots created
  during persisting of a file system; added cluster's bucket as a Volume tag

* Revamed the format for ``snaps.yaml`` allowing multiple clouds, multiple
  regions within a cloud, and multiple deployments within a region to be
  specified in the same file

* Added system message functionality to the web UI (for out-of-band status
  communication)

* Added a UI message at the start of new cluster initialization and one at the
  end of the initialization, providing more information about the status of
  the cluster and services within

* Implemented *pre-install* commands via user data (see the [User Data page][6]
  for the list of all user data options)

* Allow user data override of Galaxy's ``universe_wsgi.ini`` options

* Allow user-data override of ``nginx.conf`` (either by URL or base64 encoding
  contents in user-data)

* Added automatic (re)configuraiton of ``nginx.conf`` to reflect currenlty valid
  service paths

* Allow disabling of specific mounting by worker nodes by label in user data

* Introduced a new format for the cluster configuration file,
  ``persistent_data.yaml``

* Added an API method for retrieving the type of the cluster and CloudMan version

* Generalized ``paths.py`` to allow more paths to be overridden by a user

* Galaxy configuration is updated based on runtime settings

* Introduce notion of multiple ``service_roles``, ``name`` and ``type``, helping
  remove disambiguation with ``service_type``

* If available, run CloudMan in virtualenv (named ``CM``)

* Enabled more detailed *wsgi* error logging


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
[15]: http://wiki.galaxyproject.org/CloudMan/Hadoop
[16]: http://wiki.galaxyproject.org/CloudMan/HTCondor
[17]: http://www.loggly.com
[18]: http://bib.irb.hr/datoteka/631016.CloudMan_for_Big_Data.pdf
[19]: http://wiki.galaxyproject.org/Tool%20Shed
