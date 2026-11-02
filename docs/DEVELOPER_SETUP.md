# TRINETRA — Developer Setup & Collaboration Guide

**Platform:** Windows 10 / 11 (x64)  
**Lead Developers:** Developer 1 (Software) & Developer 2 (Hardware)  
**Private GitHub Repository:** `https://github.com/taksyastudio-gif/trinetra.git`  

---

## 1. Prerequisites & Toolchain Installation

Ensure the following tools are installed on your Windows workstation before proceeding:

1. **Git for Windows (2.40+)** with Git LFS:
   ```powershell
   winget install --id Git.Git -e --source winget
   git lfs install
   ```
2. **Python 3.10 to 3.13 (64-bit)**:
   ```powershell
   winget install --id Python.Python.3.13 -e --source winget
   ```
3. **Node.js 18+ LTS & npm**:
   ```powershell
   winget install --id OpenJS.NodeJS.LTS -e --source winget
   ```
4. **Rust & Visual Studio C++ Build Tools (Required for Tauri 2)**:
   ```powershell
   # Install Rustup
   winget install --id Rustlang.Rustup -e --source winget
   rustup default stable-x86_64-pc-windows-msvc
   ```
   *Note: Ensure "Desktop development with C++" is selected in the Visual Studio Installer.*
5. **(Hardware Devs Only) Arduino IDE 2.x or VS Code + PlatformIO**:
   ```powershell
   winget install --id Arduino.ArduinoIDE -e --source winget
   ```

---

## 2. Cloning the Repository & Initial Branch Setup

Clone the private repository using HTTPS (recommended with GitHub Credential Manager):

```powershell
# Clone the repository
git clone https://github.com/taksyastudio-gif/trinetra.git
cd trinetra

# Verify branches
git branch -a
```

### Branch Roles
- `master`: Stable, verified release branch.
- `integration`: Shared staging branch for combined testing.
- `dev/software`: Primary software development branch (Developer 1).
- `dev/hardware`: Primary hardware prototyping branch (Developer 2).

---

## 3. Workflow for Developer 1 (Software & Integration)

### Step 3.1: Switch to Software Branch
```powershell
git checkout dev/software
git pull origin dev/software
```

### Step 3.2: Python Virtual Environment Setup
```powershell
cd D:\trinetra\services\vision-engine

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install core dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3.3: Automated On-Device Model Setup
Run the verified, standalone setup script to download and cryptographically verify the YOLOX-Nano ONNX model:
```powershell
python scripts\setup_models.py

# Verify the cryptographic SHA-256 digest
python scripts\setup_models.py --check-only
```

### Step 3.4: Desktop Frontend Setup (Tauri & React)
In a new PowerShell terminal:
```powershell
cd D:\trinetra\apps\desktop

# Install node dependencies
npm install

# Verify TypeScript compilation
npm run build
```

### Step 3.5: Run the Complete Desktop Application
Start the full stack in development mode. The Rust supervisor will automatically manage the Python Vision Engine process and perform secure ephemeral token handshakes:
```powershell
cd D:\trinetra\apps\desktop
npm run tauri dev
```

### Step 3.6: Run Test Suites
```powershell
# 1. Run Python Vision Engine Tests (56 unit, integration, and recovery tests)
cd D:\trinetra\services\vision-engine
.\.venv\Scripts\python -m pytest tests -v

# 2. Run Tauri Rust Supervisor Tests
cd D:\trinetra\apps\desktop\src-tauri
cargo test
```

---

## 4. Workflow for Developer 2 (Hardware & ESP32-CAM)

### Step 4.1: Switch to Hardware Branch
```powershell
git checkout dev/hardware
git pull origin dev/hardware
```

### Step 4.2: Hardware Workspace Layout
All hardware deliverables live strictly inside the `hardware/` directory:
- `hardware/firmware/esp32-cam/`: ESP32-CAM Arduino/ESP-IDF sketches and libraries.
- `hardware/schematics/`: Wiring diagrams, pinout guides, bill of materials (BOM), and power supply schematics.
- `hardware/docs/`: Prototyping logs, rangefinder notes, and battery runtime benchmarks.

### Step 4.3: Testing ESP32-CAM MJPEG Stream Against Vision Engine
Developer 2 can run the desktop application to test the physical ESP32-CAM live:

1. Flash the ESP32-CAM with the MJPEG streaming firmware.
2. Note the ESP32 IP address from the Serial monitor (e.g. `http://192.168.1.150:81/stream`).
3. Start TRINETRA desktop:
   ```powershell
   cd D:\trinetra\apps\desktop
   npm run tauri dev
   ```
4. In the TRINETRA UI:
   - Click the **📡 Network Stream (ESP32-CAM)** tab in the top header.
   - Enter your ESP32-CAM stream URL: `http://192.168.1.150:81/stream`.
   - Click **Apply Stream URL**.
   - Click **Start Camera**.
5. Observe live detection bounding boxes and audio alerts triggered by the physical camera feed.

---

## 5. Daily Git Collaboration Protocol

To ensure seamless, collision-free collaboration without overwriting work:

```
[dev/software]                     [dev/hardware]
      |                                  |
      v                                  v
(Commit software changes)          (Commit hardware changes)
      |                                  |
      v                                  v
(Push dev/software)                (Push dev/hardware)
      \                                  /
       \                                /
        v                              v
   [GitHub PR]                    [GitHub PR]
         \                            /
          \                          /
           v                        v
        +------------------------------+
        |         integration          |  <-- Staging & E2E Validation
        +------------------------------+
                       |
                       v Pull Request
        +------------------------------+
        |            master            |  <-- Production Release
        +------------------------------+
```

### Protocol Checklist
1. **Pull Before Work:**
   ```powershell
   git pull origin <your-branch>
   ```
2. **Check Status Before Staging:**
   ```powershell
   git status
   ```
   *Never use `git add .` blindly. Stage only the files you intentionally modified.*
3. **Commit with Clear Semantic Messages:**
   ```powershell
   git commit -m "feat(hardware): implement low-latency MJPEG task on ESP32-CAM"
   ```
4. **Push to Your Designated Branch:**
   ```powershell
   git push origin dev/hardware   # For Developer 2
   # or
   git push origin dev/software   # For Developer 1
   ```
5. **Integration via Pull Requests:**
   - Go to GitHub and open a PR from your branch into `integration`.
   - Review code, verify test passes, and merge.
   - Periodically merge `integration` into `master` after hardware/software integration sign-off.
6. **Safety Rules:**
   - **NEVER** run `git reset --hard` on tracked remote branches.
   - **NEVER** run `git push --force` or `git clean -fd`.
   - Keep `.env` files and camera snapshot images local.
