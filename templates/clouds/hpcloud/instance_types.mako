<%inherit file="../amazon/instance_types.mako"/>
<%block name="instance_types">
    <select name="instance_type" id="instance_type">
        <option value=''>Same as Master</option>
        <option value='standard.xsmall'>Extra Small</option>
        <option value='standard.small'>Small</option>
        <option value='standard.medium'>Medium</option>
        <option value='standard.large'>Large</option>
        <option value='standard.xlarge'>Extra Large</option>
        <option value='standard.2xlarge'>Extra Extra Large</option>
    </select>
</%block>
