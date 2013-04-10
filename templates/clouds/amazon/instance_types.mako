<%block name="instance_types">
	 <option value='${master_instance_type}'>Same as Master (${master_instance_type})</option>
     <optgroup label="Micro Instances">
     	<option value='t1.micro' title="Cores: Up to 2 EC2 Compute Units, Memory: 613MB, IO-Perf: Low, EBS-Optimized: No">Micro (t1.micro)</option>
     </optgroup>
     <optgroup label="Standard Instances">
      <option value='m1.small' title="Cores: 1 virtual core with 1 EC2 Compute Unit, Memory: 1.7GB, IO-Perf: Moderate, EBS-Optimized: No">Small (m1.small)</option>
      <option value='m1.medium' title="Cores: 1 virtual core with 2 EC2 Compute Units, Memory: 3.75GB, IO-Perf: Moderate, EBS-Optimized: No">Medium (m1.medium)</option>
      <option value='m1.large' title="Cores: 2 virtual cores with 2 EC2 Compute Units each, Memory: 7.5GB, IO-Perf: Moderate, EBS-Optimized: 500 Mbps">Large (m1.large)</option>
      <option value='m1.xlarge' title="Cores: 4 virtual cores with 2 EC2 Compute Units each, Memory: 15GB, IO-Perf: High, EBS-Optimized: 1000 Mbps">Extra Large (m1.xlarge)</option>
     	<option value='m3.xlarge' title="Cores: 4 virtual cores with 3.25 EC2 Compute Units each, Memory: 15GB, IO-Perf: Moderate, EBS-Optimized: 500 Mbps">Extra Large (m3.xlarge)</option>
     	<option value='m3.2xlarge' title="Cores: 8 virtual cores with 3.25 EC2 Compute Units each, Memory: 30GB, IO-Perf: High, EBS-Optimized: 1000 Mbps">Double Extra Large (m3.2xlarge)</option>
     </optgroup>
     <optgroup label="High-Memory Instances">
     	<option value='m2.xlarge' title="Cores: 2 virtual cores with 3.25 EC2 Compute Units each, Memory: 17.1GB, IO-Perf: Moderate, EBS-Optimized: No">High-Memory Extra Large Instance (m2.xlarge)</option>
     	<option value='m2.2xlarge' title="Cores: 4 virtual cores with 3.25 EC2 Compute Units each, Memory: 34.2GB, IO-Perf: High, EBS-Optimized: 500 Mbps">High-Memory Double Extra Large Instance (m2.2xlarge)</option>
     	<option value='m2.4xlarge' title="Cores: 8 virtual cores with 3.25 EC2 Compute Units each, Memory: 68.4GB, IO-Perf: High, EBS-Optimized: 1000 Mbps">High-Memory Quadruple Extra Large Instance (m2.4xlarge)</option>
     </optgroup>
     <optgroup label="High-CPU Instances">
     	<option value='c1.medium' title="Cores: 2 virtual cores with 2.5 EC2 Compute Units each, Memory: 1.7GB, IO-Perf: Moderate, EBS-Optimized: No">High-CPU Medium Instance (c1.medium)</option>
     	<option value='c1.xlarge' title="Cores: 8 virtual cores with 2.5 EC2 Compute Units each, Memory: 34.2GB, IO-Perf: High, EBS-Optimized: 1000 Mbps">High-CPU Extra Large Instance (c1.xlargee)</option>
     </optgroup>
     <optgroup label="Cluster Compute Instances">
     	<option value='cc2.8xlarge' title="Cores: 2 x Intel Xeon E5-2670, eight-core, Memory: 60.5GB, IO-Perf: V. High (10 Gigabit Ethernet), EBS-Optimized: No">Cluster Compute Eight Extra Large Instance (cc2.8xlarge)</option>
     </optgroup>
     <optgroup label="High Memory Cluster Instances">
     	<option value='cr1.8xlarge' title="Cores: 2 x Intel Xeon E5-2670, eight-core. Intel Turbo, NUMA, Memory: 244GB, IO-Perf: V. High (10 Gigabit Ethernet), EBS-Optimized: No">High Memory Cluster Eight Extra Large Instance (cr1.8xlarge)</option>
     </optgroup>        
</%block>
