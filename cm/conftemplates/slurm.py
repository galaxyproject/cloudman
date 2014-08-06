SLURM_CONF_TEMPLATE = """#
# See the slurm.conf man page for more information.
#
ClusterName=GalaxyCloudMan
ControlMachine=$master_hostname
SlurmUser=slurm
SlurmctldPort=6817
SlurmdPort=6818
StateSaveLocation=$slurm_root_tmp/state
SlurmdSpoolDir=$slurm_root_tmp/slurmd_spool
SwitchType=switch/none
MpiDefault=none
SlurmctldPidFile=/var/run/slurmctld.pid
SlurmdPidFile=/var/run/slurmd.pid
ProctrackType=proctrack/pgid
CacheGroups=0
ReturnToService=0
SlurmctldTimeout=300
SlurmdTimeout=60
InactiveLimit=0
MinJobAge=300
KillWait=30
Waittime=0
SchedulerType=sched/backfill
SelectType=select/cons_res
# FastSchedule=0
TreeWidth=20
# LOGGING
SlurmctldDebug=3
SlurmdDebug=5
JobCompLoc=/var/log/slurm-llnl/jobcomp
JobCompType=jobcomp/filetxt
# COMPUTE NODES
NodeName=master NodeAddr=127.0.0.1 CPUs=$num_cpus Weight=10 State=UNKNOWN
$worker_nodes
# PARTITIONS (ie, QUEUES)
PartitionName=main Nodes=master$worker_names Default=YES MaxTime=INFINITE State=UP
"""
