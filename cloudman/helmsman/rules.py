import rules

# Delegate to keycloak in future iteration

# Permissions
rules.add_perm('helmsman.view_namespace', rules.is_staff)
rules.add_perm('helmsman.add_namespace', rules.is_staff)
rules.add_perm('helmsman.change_namespace', rules.is_staff)
rules.add_perm('helmsman.delete_namespace', rules.is_staff)

rules.add_perm('helmsman.view_chart', rules.is_staff)
rules.add_perm('helmsman.add_chart', rules.is_staff)
rules.add_perm('helmsman.change_chart', rules.is_staff)
rules.add_perm('helmsman.delete_chart', rules.is_staff)

rules.add_perm('helmsman.add_template', rules.is_staff)
rules.add_perm('helmsman.view_template', rules.is_staff)
rules.add_perm('helmsman.render_template', rules.is_staff)
rules.add_perm('helmsman.delete_template', rules.is_staff)
