<%inherit file="../amazon/instance_types.mako"/>
<%block name="instance_types">
	<option value='${master_instance_type}'>Same as Master (${master_instance_type})</option>
	<option value='m1.small' title="Cores: 1 VCPU, Memory: 4GB">Small (m1.small)</option>
    <option value='m1.medium' title="Cores: 2 VCPU, Memory: 8GB">Medium (m1.medium)</option>
    <option value='m1.large' title="Cores: 4 VCPU, Memory: 16GB">Large (m1.large)</option>
    <option value='m1.xlarge' title="Cores: 8 VCPU, Memory: 32GB">Extra Large (m1.xlarge)</option>
    <option value='m1.xxlarge' title="Cores: 16 VCPU, Memory: 64GB">Extra Large (m1.xxlarge)</option>
</%block>
