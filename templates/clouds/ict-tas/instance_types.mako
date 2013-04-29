<%inherit file="../amazon/instance_types.mako"/>
<%block name="instance_types">
    <select name="instance_type" id="instance_type">
        <option value=''>Same as Master</option>
        <option value='m1.small'>Small</option>
        <option value='m1.medium'>Medium</option>
        <option value='m1.xlarge'>Extra Large</option>
        <option value='m1.xxlarge'>Extra Extra Large</option>
    </select>
</%block>
