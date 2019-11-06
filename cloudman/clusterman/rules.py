import rules

# Delegate to keycloak in future iteration

@rules.predicate
def is_node_owner(user, node):
    # Should have update rights on the parent cluster
    if not node:
        return False
    return user.has_perm('clusters.change_cluster', node.cluster)


# Permissions
rules.add_perm('clusters.view_cluster', rules.is_staff)
rules.add_perm('clusters.add_cluster', rules.is_staff)
rules.add_perm('clusters.change_cluster', rules.is_staff)
rules.add_perm('clusters.delete_cluster', rules.is_staff)

rules.add_perm('clusternodes.view_clusternode', rules.is_staff)
rules.add_perm('clusternodes.add_clusternode', is_node_owner | rules.is_staff)
rules.add_perm('clusternodes.change_clusternode', is_node_owner | rules.is_staff)
rules.add_perm('clusternodes.delete_clusternode', is_node_owner | rules.is_staff)
