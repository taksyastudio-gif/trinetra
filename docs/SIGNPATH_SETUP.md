# Free Code Signing with SignPath Foundation (100% Free Forever, No Credit Card)

This guide explains how to get your Windows `.exe` and `.msi` installers officially signed for **$0** using the **SignPath Foundation for Open Source**.

---

## Why SignPath Foundation?
- **Cost**: $0 / year (Free forever for public open source GitHub repos)
- **Credit Card**: **Never required**
- **SmartScreen / Smart App Control**: Windows recognizes certificates issued through SignPath Foundation as trusted, preventing the "Blocked by Windows" screen.

---

## Step 1: Open-Source Requirements (Already Done ✅)
1. **Repository**: Must be public on GitHub (`https://github.com/taksyastudio-gif/trinetra`).
2. **License**: Must have an OSI-approved open source license (We already added the [MIT License](file:///d:/trinetra/LICENSE)).

---

## Step 2: Register on SignPath (2 minutes)
1. Go to **[https://signpath.org/](https://signpath.org/)** and click **Sign in with GitHub**.
2. Click **Apply for Open Source Project**.
3. Enter your repository details:
   - **Project Name**: `Trinetra`
   - **Repository URL**: `https://github.com/taksyastudio-gif/trinetra`
   - **License**: MIT
4. Once submitted, SignPath activates your open source signing policy (usually approved promptly for active GitHub projects).

---

## Step 3: Add the Free Token to GitHub
From your SignPath dashboard:
1. Copy your **API Token** and **Organization ID**.
2. Go to your GitHub repository:
   `https://github.com/taksyastudio-gif/trinetra/settings/secrets/actions`
3. Click **New repository secret**:
   - Name: `SIGNPATH_API_TOKEN`
   - Value: *(Paste your token)*
4. Click **New repository secret**:
   - Name: `SIGNPATH_ORGANIZATION_ID`
   - Value: *(Paste your Org ID)*

---

## Step 4: Automatic Signing
The GitHub Actions workflow [`.github/workflows/signpath-signing.yml`](file:///d:/trinetra/.github/workflows/signpath-signing.yml) is already created. Whenever you build a new release, SignPath will sign your `.exe` file automatically in the cloud, giving you a clean, trusted download link!
