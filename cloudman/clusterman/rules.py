import rules

# Delegate to keycloak in future iteration

@rules.predicate
def can_view_node(user, node):
    # Should have view rights on the parent cluster
    if not node:
        return False
    return user.has_perm('clusters.view_cluster', node.cluster)


@rules.predicate
def is_node_owner(user, node):
    # Should have update rights on the parent cluster
    if not node:
        return False
    return user.has_perm('clusters.change_cluster', node.cluster)


@rules.predicate
def has_autoscale_permissions(user, obj):
    return (user.has_perm('clusterman.view_cmcluster') and
            user.has_perm('clusterman.add_cmclusternode') and
            user.has_perm('clusterman.delete_cmclusternode'))


# Permissions
rules.add_perm('clusters.view_cluster', rules.is_staff | has_autoscale_permissions)
rules.add_perm('clusters.add_cluster', rules.is_staff)
rules.add_perm('clusters.change_cluster', rules.is_staff)
rules.add_perm('clusters.delete_cluster', rules.is_staff)

rules.add_perm('clusternodes.view_clusternode', can_view_node | has_autoscale_permissions | rules.is_staff)
rules.add_perm('clusternodes.add_clusternode', is_node_owner | has_autoscale_permissions | rules.is_staff)
rules.add_perm('clusternodes.change_clusternode', is_node_owner | has_autoscale_permissions | rules.is_staff)
rules.add_perm('clusternodes.delete_clusternode', is_node_owner | has_autoscale_permissions | rules.is_staff)

rules.add_perm('autoscalers.can_autoscale', has_autoscale_permissions | rules.is_staff)
