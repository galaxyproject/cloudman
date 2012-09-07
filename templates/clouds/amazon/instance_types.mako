<%block name="instance_types">
    <select name="instance_type" id="instance_type">
        <option value=''>Same as Master</option>
        <option value='t1.micro'>Micro</option>
        <option value='m1.small'>Small</option>
        <option value='m1.medium'>Medium</option>
        <option value='m1.large'>Large</option>
        <option value='m1.xlarge'>Extra Large</option>
        <option value='m2.xlarge'>High-Memory Extra Large</option>
        <option value='m2.2xlarge'>High-Memory Double Extra Large</option>
        <option value='m2.4xlarge'>High-Memory Quadruple Extra Large</option>
        ## <option value='c1.medium'>High-CPU Medium</option>
        <option value='c1.xlarge'>High-CPU Extra Large</option>
    </select>
</%block>
