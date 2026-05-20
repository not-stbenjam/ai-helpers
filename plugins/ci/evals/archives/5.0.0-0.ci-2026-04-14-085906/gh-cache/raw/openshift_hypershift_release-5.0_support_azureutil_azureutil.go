if secret == nil {
			errors = append(errors, fmt.Errorf("failed to get secret manifest for %s", config.Name))
			continue
		}

		// Create or update the secret
		if _, err := createOrUpdate(ctx, client, secret, func() error {
			// Clone base secret data to avoid mutation
			secretData := maps.Clone(baseSecretData)

			// Add the client ID if provided
			if config.ClientID != "" {
				secretData["azure_client_id"] = []byte(config.ClientID)
			}

			secret.Data = secretData
			return nil
		}); err != nil {
			errorMsg := fmt.Sprintf("failed to reconcile %s", config.ErrorContext)
			if config.ErrorContext == "" {
				errorMsg = fmt.Sprintf("failed to reconcile %s credentials", config.Name)
			}
			errors = append(errors, fmt.Errorf("%s: %w", errorMsg, err))