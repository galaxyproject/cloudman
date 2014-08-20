<%block name="instance_types_block">
    <select name="instance_type" id="instance_type">
        %for (instance_key, instance_name) in instance_types:
            <option value='${instance_key}'>${instance_name}</option>
        %endfor
    </select>
    <div id="cit_container" class="hidden" style="padding: 5px 0 10px">
        <label for="custom_instance_type">
            Enter a desired
            <a href="http://aws.amazon.com/ec2/instance-types/" target="_blank">
            instance type</a> (eg, c3.xlarge):
        </label>
        <input type="text" id="custom_instance_type" name="custom_instance_type"/>
    </div>
</%block>
