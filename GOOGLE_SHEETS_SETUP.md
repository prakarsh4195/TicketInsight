# Google Sheets Integration Setup Guide

## Method 1: Google Apps Script Web API (Recommended)

### Step 1: Create Google Apps Script

1. Open your Google Sheet with the ticket data
2. Go to **Extensions** → **Apps Script**
3. Delete any existing code and paste the following:

```javascript
function doGet(e) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(e.parameter.sheet || "Sheet1");
  const data = sheet.getDataRange().getValues();
  
  // Authentication via secret key
  if (e.parameter.key !== "YOUR_SECRET_KEY_HERE") {
    return ContentService.createTextOutput(JSON.stringify({
      'error': 'Invalid authentication'
    })).setMimeType(ContentService.MimeType.JSON);
  }
  
  return ContentService.createTextOutput(JSON.stringify({
    'data': data
  })).setMimeType(ContentService.MimeType.JSON);
}
```

4. Replace `YOUR_SECRET_KEY_HERE` with a secure random string
5. Save the script with a meaningful name

### Step 2: Deploy as Web App

1. Click **Deploy** → **New deployment**
2. Choose type: **Web app**
3. Description: "Ticket Data API"
4. Execute as: **Me**
5. Who has access: **Anyone**
6. Click **Deploy**
7. Copy the **Web app URL**

### Step 3: Configure Replit Secrets

Add these secrets to your Replit Vault:

- `GOOGLE_APPS_SCRIPT_URL`: The web app URL from step 2
- `GOOGLE_APPS_SCRIPT_KEY`: Your secret key from step 1

### Step 4: Test Integration

1. Select "Google Sheets" as data source in the dashboard
2. Click "Load Data from Google Sheets"
3. Verify data loads correctly

## Method 2: Direct API Access (Alternative)

If you prefer to use Google Sheets API directly:

### Step 1: Make Sheet Public

1. Open your Google Sheet
2. Click **Share** → **Change to anyone with the link**
3. Set permission to **Viewer**
4. Copy the sheet URL

### Step 2: Get Sheet ID

From URL: `https://docs.google.com/spreadsheets/d/SHEET_ID/edit`
Extract the SHEET_ID part

### Step 3: Configure Replit

Add to Replit Vault:
- `GOOGLE_SHEET_ID`: Your extracted sheet ID

## Troubleshooting

### Common Issues:

1. **Authentication Error**: Verify your secret key matches exactly
2. **No Data Found**: Check sheet name parameter (default: "Sheet1")
3. **Permission Error**: Ensure the Apps Script is deployed with correct permissions
4. **CORS Error**: The Apps Script handles CORS automatically

### Testing Your Setup:

Test your Apps Script URL directly in browser:
```
YOUR_WEB_APP_URL?key=YOUR_SECRET_KEY&sheet=Sheet1
```

Should return JSON with your sheet data.

## Security Notes

- Keep your secret key secure and don't share it
- The Apps Script method doesn't require sharing your sheet with external services
- You maintain full control over data access