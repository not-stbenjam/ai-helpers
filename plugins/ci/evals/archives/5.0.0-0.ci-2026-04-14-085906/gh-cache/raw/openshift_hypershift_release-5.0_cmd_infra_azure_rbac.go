type RBACManager struct {
	subscriptionID string
	creds          azcore.TokenCredential
}

// ServicePrincipalResponse represents the response from Microsoft Graph API
type ServicePrincipalResponse struct {
	Value []ServicePrincipal `json:"value"`
}

// ServicePrincipal represents a service principal from Microsoft Graph API
type ServicePrincipal struct {
	ID string `json:"id"`
}

// NewRBACManager creates a new RBACManager
func NewRBACManager(subscriptionID string, creds azcore.TokenCredential) *RBACManager {
	return &RBACManager{
		subscriptionID: subscriptionID,
		creds:          creds,
	}
}

// AssignControlPlaneRoles assigns roles to control plane managed identities
func (r *RBACManager) AssignControlPlaneRoles(ctx context.Context, opts *CreateInfraOptions, controlPlaneMIs *hyperv1.AzureResourceManagedIdentities, resourceGroupName, nsgResourceGroupName, vnetResourceGroupName string) error {
	components := map[string]hyperv1.AzureClientID{
		config.CPO:           controlPlaneMIs.ControlPlane.ControlPlaneOperator.ClientID,
		config.NodePoolMgmt:  controlPlaneMIs.ControlPlane.NodePoolManagement.ClientID,
		config.CloudProvider: controlPlaneMIs.ControlPlane.CloudProvider.ClientID,
		config.AzureFile:     controlPlaneMIs.ControlPlane.File.ClientID,
		config.AzureDisk:     controlPlaneMIs.ControlPlane.Disk.ClientID,
--
		return err
	}
	err = r.assignRole(ctx, opts.InfraID, config.AzureFile+"WI", objectID, config.AzureFileRoleDefinitionID, managedRG)
	if err != nil {
		return err
	}

	return nil
}

// assignRole assigns a scoped role to the service principal assignee
func (r *RBACManager) assignRole(ctx context.Context, infraID, component, assigneeID, role, scope string) error {
	roleAssignmentClient, err := azureauth.NewRoleAssignmentsClient(r.subscriptionID, r.creds, nil)
	if err != nil {
		return fmt.Errorf("failed to create new role assignments client: %w", err)
	}

	// Generate the role assignment name
	roleAssignmentName := util.GenerateRoleAssignmentName(infraID, component, scope)

	// Generate the role definition ID
	roleDefinitionID := fmt.Sprintf("/subscriptions/%s/providers/Microsoft.Authorization/roleDefinitions/%s", r.subscriptionID, role)

	// Generate the role assignment properties
	roleAssignmentProperties := azureauth.RoleAssignmentCreateParameters{
		Properties: &azureauth.RoleAssignmentProperties{
			PrincipalID:      ptr.To(assigneeID),
			RoleDefinitionID: ptr.To(roleDefinitionID),
			Scope:            ptr.To(scope),
		},
	}

	// Robust existence check:
	// 1) List assignments for this principalId at or around this scope and
	//    verify one matches both the exact scope and role definition ID.
	pager := roleAssignmentClient.NewListForScopePager(scope, &azureauth.RoleAssignmentsClientListForScopeOptions{
		// Use atScope() to reliably list assignments at this scope, then match in code
		Filter: ptr.To("atScope()"),
	})
	for pager.More() {
		page, err := pager.NextPage(ctx)
		if err != nil {
			return fmt.Errorf("failed to list role assignments for scope: %w", err)
		}
		for _, ra := range page.Value {
			if ra.Properties == nil {
				continue
			}
			if ra.Properties.RoleDefinitionID == nil || ra.Properties.Scope == nil || ra.Properties.PrincipalID == nil {
				continue
			}
			if strings.EqualFold(*ra.Properties.Scope, scope) && strings.EqualFold(*ra.Properties.RoleDefinitionID, roleDefinitionID) && strings.EqualFold(*ra.Properties.PrincipalID, assigneeID) {
				log.Log.Info("Skipping role assignment creation, matching assignment already exists.", "role", role, "assigneeID", assigneeID, "scope", scope)
				return nil
--
		return "", fmt.Errorf("graph API request failed with status %d: %s", resp.StatusCode, string(body))
	}

	// Parse response
	var result ServicePrincipalResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", fmt.Errorf("failed to decode response: %w", err)
	}

	if len(result.Value) == 0 {
		return "", fmt.Errorf("no object id found for client id: %s", clientID)
	}

	if len(result.Value) > 1 {
		return "", fmt.Errorf("more than one object id found for client id: %s", clientID)
	}

	return result.Value[0].ID, nil
}