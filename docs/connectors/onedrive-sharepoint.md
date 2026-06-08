# OneDrive / SharePoint Connector

The OneDrive/SharePoint connector indexes documents from Microsoft OneDrive (personal and business) and SharePoint document libraries into the AutoBot knowledge base.

## Configuration

### OneDrive Personal or OneDrive for Business

```json
{
  "connector_type": "onedrive",
  "name": "My OneDrive Documents",
  "config": {
    "token": "YOUR_OAUTH2_ACCESS_TOKEN",
    "source_type": "onedrive",
    "folder_path": "/Documents",
    "sync_subfolders": true,
    "max_file_size_mb": 100,
    "supported_extensions": [".docx", ".xlsx", ".pdf", ".pptx", ".md", ".txt"]
  },
  "enabled": true,
  "verification_mode": "collaborative"
}
```

### SharePoint Document Library

```json
{
  "connector_type": "onedrive",
  "name": "SharePoint Company Docs",
  "config": {
    "token": "YOUR_OAUTH2_ACCESS_TOKEN",
    "source_type": "sharepoint",
    "site_id": "your-site-id",
    "drive_id": "your-document-library-id",
    "folder_path": "/",
    "sync_subfolders": true
  },
  "enabled": true
}
```

## Configuration Fields

### Required Fields

- **`token`** (string): Microsoft Graph API OAuth2 access token with appropriate permissions:
  - OneDrive: `Files.Read.All` or `Files.ReadWrite.All`
  - SharePoint: `Sites.Read.All` or `Sites.ReadWrite.All`

### Optional Fields

- **`source_type`** (string): Either `"onedrive"` or `"sharepoint"`. Default: `"onedrive"`

- **`drive_id`** (string): Specific drive ID to sync. Optional for OneDrive (uses user's default drive), required for SharePoint document libraries.

- **`site_id`** (string): SharePoint site ID. Required when `source_type` is `"sharepoint"`.

- **`folder_path`** (string): Specific folder path to sync. Default: `"/"` (root).

- **`sync_subfolders`** (boolean): Recursively sync subfolders. Default: `true`.

- **`max_file_size_mb`** (integer): Skip files larger than this size in MB. Default: `100`.

- **`supported_extensions`** (array of strings): File extensions to index. Default: `[".docx", ".xlsx", ".pdf", ".pptx", ".md", ".txt"]`

## Supported File Types

The connector extracts text from the following file formats:

- **Word documents** (`.docx`) - Full text extraction from paragraphs
- **Excel spreadsheets** (`.xlsx`) - All sheets converted to text tables
- **PDF documents** (`.pdf`) - Text extraction from all pages
- **PowerPoint presentations** (`.pptx`) - Slide text extraction
- **Markdown files** (`.md`) - Raw content
- **Text files** (`.txt`) - Raw content

## Authentication

### Obtaining an Access Token

1. Register an application in Azure AD:
   - Go to [Azure Portal](https://portal.azure.com) > Azure Active Directory > App registrations
   - Click "New registration"
   - Set redirect URI (e.g., `http://localhost:8000/auth/callback`)

2. Configure API permissions:
   - For OneDrive: Add `Files.Read.All` delegated permission
   - For SharePoint: Add `Sites.Read.All` delegated permission
   - Grant admin consent if required by your organization

3. Generate access token using OAuth2 flow:
   ```bash
   # Authorization URL
   https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize?
     client_id={client_id}&
     response_type=code&
     redirect_uri={redirect_uri}&
     scope=Files.Read.All Sites.Read.All offline_access
   
   # Exchange code for token
   POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
   ```

4. Use the `access_token` from the response in the connector config.

### Token Refresh

Access tokens expire after 1 hour. For production use:
- Request `offline_access` scope to obtain a refresh token
- Implement token refresh logic in your application
- Update the connector config with the new access token

## Finding IDs

### SharePoint Site ID

```bash
# Using Microsoft Graph API
GET https://graph.microsoft.com/v1.0/sites/{hostname}:{site-path}

# Example
GET https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com:/sites/team-site
```

### SharePoint Drive (Document Library) ID

```bash
# List all drives in a site
GET https://graph.microsoft.com/v1.0/sites/{site_id}/drives

# The response contains drive IDs and names
```

## Sync Behavior

- **Incremental sync**: Only processes files that have been added or modified since the last sync
- **Change detection**: Uses `lastModifiedDateTime` comparison against Redis-cached timestamps
- **Parallel processing**: Fetches up to 4 files concurrently by default
- **Error handling**: Individual file failures don't abort the entire sync
- **Checkpoint recovery**: Resumes from last successful file on crash

## Performance

- Default concurrency: 4 parallel file fetches
- Override via `max_concurrency` field in connector config
- File size limit prevents memory issues with large files
- Redis-backed caching minimizes API calls during incremental syncs

## Troubleshooting

### 401 Unauthorized

- Token expired: Refresh the access token
- Insufficient permissions: Check API permissions in Azure AD
- Wrong tenant: Verify `tenant_id` in token acquisition

### 404 Not Found

- Invalid `site_id` or `drive_id`: Double-check IDs using Graph API
- Folder doesn't exist: Verify `folder_path` is correct

### Empty Results

- Check `supported_extensions` matches your file types
- Verify `folder_path` contains supported files
- Check `max_file_size_mb` isn't excluding all files

### Rate Limiting

- Microsoft Graph enforces per-app throttling
- Connector includes automatic retry with exponential backoff
- Consider reducing `max_concurrency` if hitting rate limits frequently

## Examples

### Sync Specific Project Folder

```json
{
  "connector_type": "onedrive",
  "name": "Project Alpha Docs",
  "config": {
    "token": "...",
    "source_type": "onedrive",
    "folder_path": "/Projects/Alpha/Documentation",
    "sync_subfolders": false,
    "supported_extensions": [".md", ".pdf"]
  }
}
```

### SharePoint HR Documents

```json
{
  "connector_type": "onedrive",
  "name": "HR Policies",
  "config": {
    "token": "...",
    "source_type": "sharepoint",
    "site_id": "contoso.sharepoint.com,abc123,def456",
    "drive_id": "b!xyz789",
    "folder_path": "/Shared Documents/HR/Policies",
    "sync_subfolders": true,
    "max_file_size_mb": 50
  }
}
```

## Related

- [Microsoft Graph API Documentation](https://docs.microsoft.com/en-us/graph/overview)
- [OneDrive API Reference](https://docs.microsoft.com/en-us/graph/api/resources/onedrive)
- [SharePoint API Reference](https://docs.microsoft.com/en-us/graph/api/resources/sharepoint)
