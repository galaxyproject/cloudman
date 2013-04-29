<%block name="instance_types_block">
    <select name="instance_type" id="instance_type">
        %for (instance_key, instance_name) in instance_types:
            <option value='${instance_key}'>${instance_name}</option>
        %endfor
    </select>
</%block>
